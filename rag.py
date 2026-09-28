import csv
import html
import json
import re
from pathlib import Path

import faiss
import numpy as np
from ollama import chat
from sentence_transformers import SentenceTransformer


ROOT = Path(__file__).resolve().parent
CORPUS_DIR = ROOT / "reports" / "hw04" / "corpus"
RAW_DIR = ROOT / "reports" / "hw04" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

MODEL_NAME = "qwen3:8b"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50


QUESTIONS = [
    {
        "id": "Q1",
        "question": "What fields should a useful transit incident record contain?",
        "targets": ["transit_data_quality.txt"],
        "keywords": ["identifier", "date", "route", "category"],
        "needs_refusal": False,
    },
    {
        "id": "Q2",
        "question": "What should happen immediately after a transit incident, and what information should be recorded?",
        "targets": ["transit_incident_response.txt", "transit_data_quality.txt"],
        "keywords": ["protect", "passenger", "record", "description"],
        "needs_refusal": False,
    },
    {
        "id": "Q3",
        "question": "How do consistent incident categories help transit agencies?",
        "targets": ["transit_safety_basics.txt", "transit_data_quality.txt"],
        "keywords": ["category", "analysis", "compare"],
        "needs_refusal": False,
    },
    {
        "id": "Q4",
        "question": "What does a major transit event mean?",
        "targets": ["transit_safety_basics.txt"],
        "keywords": ["serious", "report", "investigation"],
        "needs_refusal": False,
    },
    {
        "id": "Q5",
        "question": "What is the exact fare for VTA Route 55?",
        "targets": [],
        "keywords": [],
        "needs_refusal": True,
    },
    {
        "id": "Q6",
        "question": "Who won the 2025 World Series?",
        "targets": [],
        "keywords": [],
        "needs_refusal": True,
    },
]


def clean_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")

    if path.suffix.lower() == ".html":
        text = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)

    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def make_chunks(text: str) -> list[str]:
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(text[start:end])

        if end == len(text):
            break

        start = end - CHUNK_OVERLAP

    return chunks


def load_corpus():
    records = []

    for path in sorted(CORPUS_DIR.iterdir()):
        if not path.is_file():
            continue

        text = clean_text(path)

        for chunk_id, chunk in enumerate(make_chunks(text)):
            records.append(
                {
                    "source": path.name,
                    "chunk_id": chunk_id,
                    "text": chunk,
                }
            )

    return records


def build_index(records):
    model = SentenceTransformer(EMBEDDING_MODEL)
    texts = [record["text"] for record in records]

    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    vectors = np.asarray(vectors, dtype="float32")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)

    return model, index


def retrieve(question, model, index, records, top_k):
    vector = model.encode(
        [question],
        normalize_embeddings=True,
    )

    vector = np.asarray(vector, dtype="float32")
    scores, positions = index.search(vector, top_k)

    results = []

    for score, position in zip(scores[0], positions[0]):
        record = records[int(position)].copy()
        record["score"] = round(float(score), 4)
        results.append(record)

    return results


def ask_llm(prompt):
    response = chat(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )

    return response["message"]["content"].strip()


def context_text(results, engineered=False):
    if not engineered:
        return "\n\n".join(
            f"Source: {item['source']}\n{item['text']}"
            for item in results
        )

    unique = []
    seen = set()

    for item in results:
        key = item["text"].strip()

        if key not in seen:
            seen.add(key)
            unique.append(item)

    parts = []

    for number, item in enumerate(unique, start=1):
        parts.append(
            f"[Source {number}: {item['source']}]\n{item['text']}"
        )

    return "\n\n".join(parts)


def save_jsonl(filename, rows):
    path = RAW_DIR / filename

    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def evaluate(question, config, answer, retrieved):
    target_sources = question["targets"]
    answer_lower = answer.lower()

    if target_sources:
        correct_retrieval = any(
            item["source"] in target_sources for item in retrieved
        )
    else:
        correct_retrieval = False

    if question["needs_refusal"]:
        correct_answer = (
            "i cannot answer this question from the provided documents"
            in answer_lower
        )
        refused_when_needed = correct_answer
    else:
        keyword_matches = sum(
            keyword in answer_lower for keyword in question["keywords"]
        )
        correct_answer = keyword_matches >= 1
        refused_when_needed = True

    grounded = (
        config == "context_rag"
        and (
            question["needs_refusal"]
            or "[source" in answer_lower
        )
    )

    return {
        "question": question["id"],
        "configuration": config,
        "correct_retrieval": correct_retrieval,
        "correct_answer": correct_answer,
        "grounded": grounded,
        "refused_when_needed": refused_when_needed,
    }


def main():
    records = load_corpus()

    print(f"Loaded {len(records)} chunks from {len(list(CORPUS_DIR.iterdir()))} documents.")

    model, index = build_index(records)

    retrieval_rows = []
    comparison_rows = []
    evaluation_rows = []

    for question in QUESTIONS:
        retrieved = retrieve(
            question["question"],
            model,
            index,
            records,
            top_k=15,
        )

        print("\nRETRIEVAL")
        print(json.dumps(
            {
                "question": question["id"],
                "text": question["question"],
                "chunks": retrieved,
            },
            indent=2,
            ensure_ascii=False,
        ))

        retrieval_rows.append(
            {
                "question": question["id"],
                "question_text": question["question"],
                "retrieved_chunks": retrieved,
            }
        )

        no_rag_prompt = f"""
Answer this question directly:

{question["question"]}
"""

        basic_prompt = f"""
Answer the question using the context below.

Question:
{question["question"]}

Context:
{context_text(retrieved)}
"""

        context_rag_prompt = f"""
You are a grounded question-answering assistant.

Use the supplied context to answer the question. The evidence may be indirect
or spread across multiple retrieved chunks, so combine related information
carefully. Do not use outside knowledge.

Cite the source number in your answer when possible.

Only respond exactly with:
I cannot answer this question from the provided documents

when the context is clearly unrelated to the question or contains no useful
evidence. Do not refuse a question merely because the wording is different
from the context.

Question:
{question["question"]}

Context:
{context_text(retrieved, engineered=True)}
"""

        answers = {
            "no_rag": ask_llm(no_rag_prompt),
            "basic_rag": ask_llm(basic_prompt),
            "context_rag": ask_llm(context_rag_prompt),
        }

        for configuration, answer in answers.items():
            row = {
                "question": question["id"],
                "question_text": question["question"],
                "configuration": configuration,
                "answer": answer,
            }

            comparison_rows.append(row)

            evaluation_rows.append(
                evaluate(
                    question,
                    configuration,
                    answer,
                    retrieved,
                )
            )

    save_jsonl("retrieved_chunks.jsonl", retrieval_rows)
    save_jsonl("rag_comparison.jsonl", comparison_rows)

    sweep_rows = []

    sweep_question = QUESTIONS[0]

    for k in [1, 3, 5]:
        results = retrieve(
            sweep_question["question"],
            model,
            index,
            records,
            top_k=k,
        )

        prompt = f"""
Answer only from the context below and cite the source number.

Question:
{sweep_question["question"]}

Context:
{context_text(results, engineered=True)}
"""

        sweep_rows.append(
            {
                "question": sweep_question["id"],
                "k": k,
                "retrieved_chunks": results,
                "answer": ask_llm(prompt),
            }
        )

    save_jsonl("k_sweep.jsonl", sweep_rows)

    with (RAW_DIR / "evaluation_table.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as stream:
        fieldnames = [
            "question",
            "configuration",
            "correct_retrieval",
            "correct_answer",
            "grounded",
            "refused_when_needed",
        ]

        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(evaluation_rows)

    print("\nSaved RAG outputs to:")
    print(RAW_DIR / "retrieved_chunks.jsonl")
    print(RAW_DIR / "rag_comparison.jsonl")
    print(RAW_DIR / "k_sweep.jsonl")
    print(RAW_DIR / "evaluation_table.csv")


if __name__ == "__main__":
    main()