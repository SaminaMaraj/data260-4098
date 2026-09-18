"""Run the HW3 retrieval-only comparison for three LlamaIndex chunkers."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from bs4 import BeautifulSoup
from llama_index.core import Document, VectorStoreIndex
from llama_index.core.node_parser import (
    SemanticSplitterNodeParser,
    SentenceWindowNodeParser,
    TokenTextSplitter,
)
from llama_index.core.schema import MetadataMode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding


REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "reports" / "hw03"
CORPUS_DIR = REPORT_DIR / "corpus"
RAW_DIR = REPORT_DIR / "raw"
QUESTIONS_PATH = REPORT_DIR / "questions.yaml"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 5


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_questions() -> list[dict[str, Any]]:
    data = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))
    return list(data["questions"])


def load_documents() -> list[Document]:
    documents: list[Document] = []
    for path in sorted(CORPUS_DIR.iterdir()):
        if not path.is_file():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() in {".html", ".htm"}:
            text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
        else:
            text = raw
        documents.append(
            Document(
                text=text,
                metadata={"source_file": path.name, "byte_size": path.stat().st_size},
            )
        )
    if not documents:
        raise FileNotFoundError(f"No corpus files found in {CORPUS_DIR}")
    return documents


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def local_sentence_splitter(text: str) -> list[str]:
    """Split sentences locally without requiring an NLTK data download."""
    pieces = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [piece.strip() for piece in pieces if piece.strip()]


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    if denominator == 0:
        return 0.0
    return float(np.dot(a, b) / denominator)


def chunkers(embed_model: HuggingFaceEmbedding) -> dict[str, Any]:
    return {
        "Token": TokenTextSplitter(chunk_size=256, chunk_overlap=32),
        "Semantic": SemanticSplitterNodeParser.from_defaults(
            buffer_size=1,
            breakpoint_percentile_threshold=95,
            sentence_splitter=local_sentence_splitter,
            embed_model=embed_model,
        ),
        "Sentence-window": SentenceWindowNodeParser.from_defaults(
            window_size=2,
            window_metadata_key="window",
            original_text_metadata_key="original_sentence",
            sentence_splitter=local_sentence_splitter,
        ),
    }


def node_source(node: Any) -> str:
    return str(node.metadata.get("source_file", "unknown"))


def build_pipeline(
    technique: str,
    parser: Any,
    documents: list[Document],
    embed_model: HuggingFaceEmbedding,
) -> tuple[VectorStoreIndex, list[Any]]:
    nodes = parser.get_nodes_from_documents(documents)
    index = VectorStoreIndex(nodes, embed_model=embed_model)
    print(f"{technique}: chunks={len(nodes)}")
    return index, nodes


def retrieve_one(
    technique: str,
    index: VectorStoreIndex,
    nodes: list[Any],
    question: dict[str, Any],
    embed_model: HuggingFaceEmbedding,
    k: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    query = question["question"]
    query_vector = np.asarray(embed_model.get_query_embedding(query), dtype=np.float32)
    retriever = index.as_retriever(similarity_top_k=k)
    start = time.perf_counter()
    retrieved = retriever.retrieve(query)
    latency_ms = (time.perf_counter() - start) * 1000

    rows: list[dict[str, Any]] = []
    for rank, result in enumerate(retrieved, start=1):
        text = result.node.get_content(metadata_mode=MetadataMode.NONE)
        document_vector = np.asarray(embed_model.get_text_embedding(text), dtype=np.float32)
        rows.append(
            {
                "rank": rank,
                "store_score": float(result.score) if result.score is not None else None,
                "cosine_sim": cosine_similarity(query_vector, document_vector),
                "chunk_len": len(text),
                "preview": text[:160].replace("\n", " "),
                "source_file": node_source(result.node),
                "contains_expected_keyword": any(
                    normalize(keyword) in normalize(text)
                    for keyword in question.get("answer_keywords", [])
                ),
            }
        )

    answer_hit = any(row["contains_expected_keyword"] for row in rows)
    source_hit = any(row["source_file"] == question["expected_source_file"] for row in rows)
    summary = {
        "question_id": question["id"],
        "question": query,
        "technique": technique,
        "query_shape": [int(query_vector.shape[0])],
        "query_first_8": query_vector[:8].tolist(),
        "doc_vector_shape": [len(rows), int(query_vector.shape[0])],
        "chunk_count": len(nodes),
        "avg_chunk_length": float(np.mean([len(node.get_content()) for node in nodes])),
        "retrieval_latency_ms": latency_ms,
        "top1_cosine": rows[0]["cosine_sim"] if rows else None,
        "mean_at_k_cosine": float(np.mean([row["cosine_sim"] for row in rows])) if rows else None,
        "recall_at_k": int(answer_hit and source_hit),
        "expected_source_file": question["expected_source_file"],
        "answer_keyword_hit": answer_hit,
        "source_file_hit": source_hit,
    }
    return summary, rows


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    questions = load_questions()
    documents = load_documents()
    print(f"Loaded {len(documents)} corpus documents and {len(questions)} questions.")
    embed_model = HuggingFaceEmbedding(
        model_name=MODEL_NAME,
        embed_batch_size=64,
        device="cpu",
    )
    print(f"Embedding model ready: {MODEL_NAME}")
    pipelines = {}
    for technique, parser in chunkers(embed_model).items():
        print(f"Building {technique} index ...", flush=True)
        pipelines[technique] = build_pipeline(technique, parser, documents, embed_model)

    all_summaries: list[dict[str, Any]] = []
    all_rows: list[dict[str, Any]] = []
    for question in questions:
        for technique, (index, nodes) in pipelines.items():
            print(f"Retrieving {question['id']} with {technique} ...", flush=True)
            summary, rows = retrieve_one(technique, index, nodes, question, embed_model, TOP_K)
            all_summaries.append(summary)
            for row in rows:
                all_rows.append({**summary, **row})
            print(
                f"{technique:16} {question['id']} "
                f"top1={summary['top1_cosine']:.4f} "
                f"mean@{TOP_K}={summary['mean_at_k_cosine']:.4f} "
                f"latency_ms={summary['retrieval_latency_ms']:.2f}"
            )

    (RAW_DIR / "retrieval_summaries.json").write_text(
        json.dumps({"generated_at": utc_now(), "model": MODEL_NAME, "summaries": all_summaries}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    with (RAW_DIR / "retrieval_outputs.jsonl").open("w", encoding="utf-8") as stream:
        for row in all_rows:
            stream.write(json.dumps(row) + "\n")

    misleading = [
        row
        for row in all_rows
        if row["rank"] == 1 and not row["contains_expected_keyword"]
    ]
    (RAW_DIR / "misleading_candidates.json").write_text(
        json.dumps(misleading[:10], indent=2) + "\n", encoding="utf-8"
    )
    print(f"Saved {len(all_summaries)} summaries and {len(all_rows)} retrieval rows.")
    print(f"Misleading top-1 candidates: {len(misleading)}")


if __name__ == "__main__":
    main()
