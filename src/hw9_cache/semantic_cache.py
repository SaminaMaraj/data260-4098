"""HW9 Part 2: semantic response cache stored in Redis with a vector index.

One Redis hash per cached answer, key  s4098:semcache:<id>  with fields
    query, answer, data_version, deps (JSON), created_at, embedding (FLOAT32 bytes)
The index s4098:idx:semcache (Redis query engine, FLAT, COSINE, 384 dims)
answers a KNN-1 query; Redis returns the cosine *distance*, so
similarity = 1 - distance.

MemoryBackend has the same interface and is only used by the offline tests
(no Redis Stack needed there).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field

import numpy as np

from src.hw9_cache.config import (
    CACHE_INDEX,
    CACHE_KEY_PREFIX,
    CACHE_TTL_SECONDS,
    EMBED_DIM,
)

RETURN_FIELDS = ["query", "answer", "data_version", "deps", "created_at", "dist"]


@dataclass
class CacheEntry:
    key: str
    query: str
    answer: str
    data_version: str
    deps: dict = field(default_factory=dict)
    created_at: float = 0.0
    similarity: float = 0.0


# --------------------------------------------------------------------- Redis
class RedisVectorBackend:
    def __init__(
        self,
        client,
        index: str = CACHE_INDEX,
        prefix: str = CACHE_KEY_PREFIX,
        dim: int = EMBED_DIM,
        ttl: int = CACHE_TTL_SECONDS,
    ):
        self.r = client
        self.index = index
        self.prefix = prefix
        self.dim = dim
        self.ttl = ttl
        self.ensure_index()

    def ensure_index(self) -> None:
        from redis.commands.search.field import (
            NumericField,
            TagField,
            TextField,
            VectorField,
        )

        try:
            from redis.commands.search.index_definition import (
                IndexDefinition,
                IndexType,
            )
        except ImportError:  # redis-py < 6
            from redis.commands.search.indexDefinition import IndexDefinition, IndexType

        try:
            self.r.ft(self.index).info()
            return
        except Exception:  # noqa: BLE001 - "Unknown index name"
            pass
        schema = (
            TextField("query"),
            TextField("answer"),
            TagField("data_version"),
            TextField("deps"),
            NumericField("created_at"),
            VectorField(
                "embedding",
                "FLAT",
                {"TYPE": "FLOAT32", "DIM": self.dim, "DISTANCE_METRIC": "COSINE"},
            ),
        )
        self.r.ft(self.index).create_index(
            schema,
            definition=IndexDefinition(prefix=[self.prefix], index_type=IndexType.HASH),
        )

    def add(
        self, query: str, vector: np.ndarray, answer: str, data_version: str, deps: dict
    ) -> str:
        key = f"{self.prefix}{uuid.uuid4().hex[:12]}"
        self.r.hset(
            key,
            mapping={
                "query": query,
                "answer": answer,
                "data_version": data_version,
                "deps": json.dumps(deps, sort_keys=True),
                "created_at": time.time(),
                "embedding": np.asarray(vector, dtype=np.float32).tobytes(),
            },
        )
        if self.ttl:
            self.r.expire(key, self.ttl)
        return key

    def nearest(self, vector: np.ndarray) -> CacheEntry | None:
        from redis.commands.search.query import Query

        q = (
            Query("*=>[KNN 1 @embedding $vec AS dist]")
            .sort_by("dist")
            .return_fields(*RETURN_FIELDS)
            .paging(0, 1)
            .dialect(2)
        )
        res = self.r.ft(self.index).search(
            q, query_params={"vec": np.asarray(vector, dtype=np.float32).tobytes()}
        )
        if not res.docs:
            return None
        d = res.docs[0]
        return CacheEntry(
            key=d.id,
            query=d.query,
            answer=d.answer,
            data_version=d.data_version,
            deps=json.loads(d.deps or "{}"),
            created_at=float(d.created_at or 0),
            similarity=round(1.0 - float(d.dist), 4),
        )

    def delete(self, key: str) -> None:
        self.r.delete(key)

    def flush(self) -> int:
        keys = list(self.r.scan_iter(match=f"{self.prefix}*", count=500))
        if keys:
            self.r.delete(*keys)
        return len(keys)

    def size(self) -> int:
        return int(self.r.ft(self.index).info().get("num_docs", 0))


# ----------------------------------------------------- offline-test backend
class MemoryBackend:
    def __init__(self):
        self.items: dict[str, tuple[np.ndarray, CacheEntry]] = {}

    def add(self, query, vector, answer, data_version, deps) -> str:
        key = f"{CACHE_KEY_PREFIX}{uuid.uuid4().hex[:12]}"
        self.items[key] = (
            np.asarray(vector, dtype=np.float32),
            CacheEntry(key, query, answer, data_version, deps, time.time()),
        )
        return key

    def nearest(self, vector) -> CacheEntry | None:
        best, best_sim = None, -2.0
        for vec, entry in self.items.values():
            sim = float(
                np.dot(vec, vector) / (np.linalg.norm(vec) * np.linalg.norm(vector))
            )
            if sim > best_sim:
                best, best_sim = entry, sim
        if best is None:
            return None
        return CacheEntry(**{**best.__dict__, "similarity": round(best_sim, 4)})

    def delete(self, key) -> None:
        self.items.pop(key, None)

    def flush(self) -> int:
        n = len(self.items)
        self.items.clear()
        return n

    def size(self) -> int:
        return len(self.items)


class SemanticCache:
    """Threshold logic on top of a vector backend."""

    def __init__(self, backend, threshold: float):
        self.backend = backend
        self.threshold = threshold

    def lookup(self, vector) -> tuple[CacheEntry | None, CacheEntry | None]:
        """Returns (hit or None, nearest entry or None)."""
        nearest = self.backend.nearest(vector)
        if nearest is not None and nearest.similarity >= self.threshold:
            return nearest, nearest
        return None, nearest

    def store(self, query, vector, answer, data_version, deps) -> str:
        return self.backend.add(query, vector, answer, data_version, deps)
