"""Query embeddings for the semantic cache.

Default: SentenceTransformers all-MiniLM-L6-v2 (384 dims, unit-normalized, so
cosine similarity = dot product). HW9_EMBEDDER=stub gives a deterministic
hashed bag-of-words vector that is only used by the offline tests.
"""

from __future__ import annotations

import hashlib
import os
import re

import numpy as np

from src.hw9_cache.config import EMBED_DIM, EMBED_MODEL


class Embedder:
    def __init__(self, kind: str | None = None):
        self.kind = kind or os.environ.get("HW9_EMBEDDER", "st")
        self.model_name = EMBED_MODEL if self.kind == "st" else "stub-hash-bow"
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(EMBED_MODEL)
        return self._model

    def warm_up(self) -> None:
        if self.kind == "st":
            self.embed("warm up")

    def embed(self, text: str) -> np.ndarray:
        if self.kind == "stub":
            return _stub_vector(text)
        vec = self._load().encode(text, normalize_embeddings=True)
        return np.asarray(vec, dtype=np.float32)


def _stub_vector(text: str) -> np.ndarray:
    words = re.findall(r"[a-z0-9-]+", text.lower())
    grams = words + [f"{a} {b}" for a, b in zip(words, words[1:])]
    vec = np.zeros(EMBED_DIM, dtype=np.float32)
    for g in grams:
        h = int(hashlib.md5(g.encode()).hexdigest(), 16)
        vec[h % EMBED_DIM] += 1.0 if (h >> 9) % 2 else -1.0
    norm = np.linalg.norm(vec)
    return vec / norm if norm else vec


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(np.dot(a, b) / (na * nb)) if na and nb else 0.0
