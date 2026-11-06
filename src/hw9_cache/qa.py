"""HW9 Part 2/3: the cached Q&A ingress in front of the HW8 agent pipeline.

ask(question):
  1. embed the query                      (SentenceTransformers)
  2. KNN-1 search in the Redis vector index (cosine similarity)
  3. similarity >= threshold  -> cache HIT
       (invalidation="version") re-read the records the cached answer
       depends on; if their data_version changed the entry is stale ->
       delete it and continue as a miss
       otherwise return the stored answer, is_cached=True
  4. otherwise cache MISS -> ground the question in s4098_rel, run the HW8
     Planner->Writer->Reviewer path, store query + embedding + answer +
     data_version, return is_cached=False
Every step is timed with perf_counter; latency_ms is the whole request.
"""

from __future__ import annotations

import time

from src.hw9_cache.agent_path import AgentPath
from src.hw9_cache.config import log, ms_since
from src.hw9_cache.embeddings import Embedder
from src.hw9_cache.facts import FactStore
from src.hw9_cache.semantic_cache import SemanticCache

C = "QA"


class CachedQA:
    def __init__(
        self,
        cache: SemanticCache,
        facts: FactStore,
        agent: AgentPath,
        embedder: Embedder,
        invalidation: str = "version",  # "version" or "none"
        store_on_miss: bool = True,
        verbose: bool = True,
    ):
        self.cache = cache
        self.facts = facts
        self.agent = agent
        self.embedder = embedder
        self.invalidation = invalidation
        self.store_on_miss = store_on_miss
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            log(C, msg)

    def ask(self, question: str) -> dict:
        t_start = time.perf_counter()
        timings: dict[str, float] = {}

        t = time.perf_counter()
        vector = self.embedder.embed(question)
        timings["embed_ms"] = ms_since(t)

        t = time.perf_counter()
        hit, nearest = self.cache.lookup(vector)
        timings["search_ms"] = ms_since(t)
        best_sim = nearest.similarity if nearest else 0.0
        result = {
            "question": question,
            "threshold": self.cache.threshold,
            "similarity": best_sim,
            "nearest_query": nearest.query if nearest else None,
            "invalidated": False,
        }

        if hit is not None and self.invalidation == "version":
            t = time.perf_counter()
            current = self.facts.load_facts(hit.deps).data_version
            timings["version_check_ms"] = ms_since(t)
            if current != hit.data_version:
                self._log(
                    f"STALE entry {hit.key}: stored data_version={hit.data_version} "
                    f"current={current} -> invalidate and recompute"
                )
                self.cache.backend.delete(hit.key)
                result["invalidated"] = True
                result["stale_data_version"] = hit.data_version
                hit = None

        if hit is not None:
            result.update(
                answer=hit.answer,
                is_cached=True,
                matched_query=hit.query,
                matched_key=hit.key,
                data_version=hit.data_version,
                deps=hit.deps,
            )
            timings["total_ms"] = ms_since(t_start)
            result["latency_ms"] = timings["total_ms"]
            result["timings"] = timings
            self._log(
                f"CACHE HIT  similarity={best_sim:.4f} >= {self.cache.threshold} "
                f'matched="{hit.query}" latency={result["latency_ms"]} ms'
            )
            return result

        self._log(
            f"CACHE MISS best_similarity={best_sim:.4f} < {self.cache.threshold}"
            if not result["invalidated"]
            else "CACHE MISS (stale entry invalidated)"
        )
        t = time.perf_counter()
        grounding = self.facts.ground(question)
        timings["grounding_ms"] = ms_since(t)

        agent_out = self.agent.run(question, grounding.as_prompt())
        timings["agent_ms"] = agent_out["agent_ms"]

        key = None
        if self.store_on_miss:
            t = time.perf_counter()
            key = self.cache.store(
                question,
                vector,
                agent_out["answer"],
                grounding.data_version,
                grounding.deps,
            )
            timings["store_ms"] = ms_since(t)

        timings["total_ms"] = ms_since(t_start)
        result.update(
            answer=agent_out["answer"],
            is_cached=False,
            matched_query=None,
            stored_key=key,
            data_version=grounding.data_version,
            deps=grounding.deps,
            facts=grounding.lines,
            agent_status=agent_out.get("status"),
            agent_stage_ms=agent_out.get("stage_ms"),
            latency_ms=timings["total_ms"],
            timings=timings,
        )
        self._log(
            f"agent answered in {timings['agent_ms']} ms; "
            + (
                f"stored {key} data_version={grounding.data_version}"
                if key
                else "not stored (read-only run)"
            )
            + f"; latency={result['latency_ms']} ms"
        )
        return result


def build_qa(
    threshold: float,
    *,
    invalidation: str = "version",
    store_on_miss=True,
    agent_mode: str = "inproc",
    llm: str = "real",
    backend: str = "redis",
    verbose: bool = True,
) -> CachedQA:
    """Wire everything with the real services (Redis Stack, s4098_rel, Ollama)."""
    from src.hw9_cache.db import get_engine, get_redis
    from src.hw9_cache.semantic_cache import MemoryBackend, RedisVectorBackend

    vec_backend = (
        RedisVectorBackend(get_redis()) if backend == "redis" else MemoryBackend()
    )
    embedder = Embedder()
    embedder.warm_up()
    return CachedQA(
        SemanticCache(vec_backend, threshold),
        FactStore(get_engine()),
        AgentPath(agent_mode, llm),
        embedder,
        invalidation=invalidation,
        store_on_miss=store_on_miss,
        verbose=verbose,
    )
