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