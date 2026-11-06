"""HW9 configuration: PREFIX, Redis keys and the shared log/banner helpers.

Every Redis key used in HW9 starts with PREFIX (s4098), the same personal
configuration as HW1-HW8 (src/hw8_kafka/config.py).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from src.hw8_kafka.config import PORT_BASE, PREFIX, SEED, SID4, STUDENT_NAME

__all__ = ["PORT_BASE", "PREFIX", "SEED", "SID4", "STUDENT_NAME"]

# Redis Stack (Redis + the query engine for the vector index), see docker-compose.hw9.yml
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6380/0")

# Part 1 - view counter
VIEW_KEY = PREFIX + ":views:incident:{incident_id}"
SYNC_EVERY = 10

# Part 2/3 - semantic cache
CACHE_KEY_PREFIX = f"{PREFIX}:semcache:"
CACHE_INDEX = f"{PREFIX}:idx:semcache"
DEFAULT_THRESHOLD = 0.85
CACHE_TTL_SECONDS = int(os.environ.get("HW9_CACHE_TTL", str(24 * 3600)))

# SentenceTransformers model (same model as HW3 retrieval); 384-dim vectors
EMBED_MODEL = os.environ.get(
    "HW9_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
EMBED_DIM = 384

# API wrapper for the cached Q&A endpoint (HW8 API already uses PORT_BASE)
QA_PORT = PORT_BASE + 1  # 8499


def now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def log(component: str, message: str) -> None:
    print(f"{now_iso()} [{component}] {message}", flush=True)


def banner(script: str) -> None:
    print(
        f"{STUDENT_NAME} | {script} | PREFIX={PREFIX} REDIS={REDIS_URL}",
        flush=True,
    )


def ms_since(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)
