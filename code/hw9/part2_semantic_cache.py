"""HW9 Part 2: semantic cache in front of the HW8 agent path - 12 test queries.

    python code/hw9/part2_semantic_cache.py                 # threshold 0.85, inproc agents
    python code/hw9/part2_semantic_cache.py --agent-path kafka   # through the HW8 Kafka agents

Empties the s4098:semcache:* entries first, then sends 12 queries (new questions,
exact duplicates, paraphrases) in order. Misses are answered by the agent path
and stored; later duplicates/paraphrases should be served from Redis.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.hw9_cache.config import DEFAULT_THRESHOLD, banner  # noqa: E402
from src.hw9_cache.qa import build_qa  # noqa: E402

RAW = ROOT / "reports" / "hw09" / "raw"

QUERIES = [
    ("new", "How many delay incidents were recorded on VTA Route 22?"),
    ("new", "Who operates VTA Route 522?"),
    (
        "exact duplicate of #1",
        "How many delay incidents were recorded on VTA Route 22?",
    ),
    (
        "paraphrase of #1",
        "What is the number of delay incidents logged for VTA Route 22?",
    ),
    ("new", "What category is incident INC-000042?"),
    ("paraphrase of #2", "Which operator runs VTA Route 522?"),
    ("exact duplicate of #5", "What category is incident INC-000042?"),
    ("new", "How many incidents in total were recorded on VTA Route 55?"),
    ("paraphrase of #8", "What is the total incident count for VTA Route 55?"),
    ("new (unrelated)", "What is the capital of Australia?"),
    ("exact duplicate of #2", "Who operates VTA Route 522?"),
    ("paraphrase of #5", "Which incident category does INC-000042 belong to?"),
]


def short(text: str, n: int = 150) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 3] + "..."


def main(args) -> int:
    banner("part2_semantic_cache.py (Part 2)")
    qa = build_qa(
        args.threshold, agent_mode=args.agent_path, llm=args.llm, backend=args.backend
    )
    removed = qa.cache.backend.flush()
    print(
        f"threshold={args.threshold}  embedder={qa.embedder.model_name}  "
        f"agent path={args.agent_path}  (flushed {removed} old cache entries)\n"
    )

    rows = []
    for i, (kind, query) in enumerate(QUERIES, 1):
        print(f"--- #{i:02d} [{kind}] {query}")
        res = qa.ask(query)
        res["n"], res["kind"] = i, kind
        rows.append(res)
        print(
            f"    is_cached={res['is_cached']}  similarity={res['similarity']:.4f}  "
            f"latency={res['latency_ms']:.1f} ms"
            + (f'  matched="{res["matched_query"]}"' if res["is_cached"] else "")
        )
        print(f"    answer: {short(res['answer'])}\n")

    hits = [r for r in rows if r["is_cached"]]
    misses = [r for r in rows if not r["is_cached"]]
    summary = {
        "threshold": args.threshold,
        "queries": len(rows),
        "hits": len(hits),
        "misses": len(misses),
        "hit_rate_pct": round(100 * len(hits) / len(rows), 1),
        "avg_latency_cached_ms": round(
            statistics.mean(r["latency_ms"] for r in hits), 2
        )
        if hits
        else None,
        "avg_latency_uncached_ms": round(
            statistics.mean(r["latency_ms"] for r in misses), 2
        )
        if misses
        else None,
        "embedder": qa.embedder.model_name,
        "agent_path": args.agent_path,
    }
    if hits and misses:
        summary["observed_speedup_x"] = round(
            summary["avg_latency_uncached_ms"] / summary["avg_latency_cached_ms"], 1
        )

    print("=== Summary table ===")
    print(
        f"{'#':>3} {'kind':<24} {'is_cached':<9} {'similarity':>10} {'latency ms':>11}"
    )
    for r in rows:
        print(
            f"{r['n']:>3} {r['kind']:<24} {str(r['is_cached']):<9} "
            f"{r['similarity']:>10.4f} {r['latency_ms']:>11.1f}"
        )
    print(
        f"\nCache hit rate: {summary['hits']}/{summary['queries']} = "
        f"{summary['hit_rate_pct']}%"
    )
    print(
        f"Average latency cached:     {summary['avg_latency_cached_ms']} ms "
        f"({len(hits)} queries)"
    )
    print(
        f"Average latency non-cached: {summary['avg_latency_uncached_ms']} ms "
        f"({len(misses)} queries)"
    )
    if "observed_speedup_x" in summary:
        print(f"Observed ratio non-cached / cached: {summary['observed_speedup_x']}x")

    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "part2_results.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, default=str)
    )
    print(f"\nsaved {RAW / 'part2_results.json'}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    p.add_argument("--agent-path", choices=["inproc", "kafka"], default="inproc")
    p.add_argument("--llm", choices=["real", "stub"], default="real")
    p.add_argument("--backend", choices=["redis", "memory"], default="redis")
    raise SystemExit(main(p.parse_args()))
