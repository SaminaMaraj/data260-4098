"""HW9 Part 3.2: threshold sweep over the 40 labeled cases in cache_cases.yaml.

    python code/hw9/part3_threshold_sweep.py                    # 0.75 0.80 0.85 0.90 0.95
    python code/hw9/part3_threshold_sweep.py --thresholds 0.90  # one threshold (resume)

For every threshold: empty the cache, store the 10 seeds, then send the 40 cases
read-only (a miss runs the HW8 agent path live but is not stored). One file per
threshold is written to reports/hw09/raw/part3_sweep_<t>.json; an existing file is
skipped unless --force, so an interrupted sweep can be resumed.

The seed answers are produced once by the agent path (part3_seed_answers.json) and
re-stored for every threshold, so all thresholds compare against identical entries.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.hw9_cache.config import banner, log  # noqa: E402
from src.hw9_cache.qa import build_qa  # noqa: E402

RAW = ROOT / "reports" / "hw09" / "raw"
CASES = ROOT / "reports" / "hw09" / "cases" / "cache_cases.yaml"
SEED_FILE = RAW / "part3_seed_answers.json"
C = "SWEEP"


def load_cases():
    data = yaml.safe_load(CASES.read_text())
    seeds, cases = data["seeds"], data["cases"]
    assert len(seeds) == 10 and len(cases) == 40, (
        "cache_cases.yaml must have 10 seeds/40 cases"
    )
    groups = {}
    for c in cases:
        groups[c["group"]] = groups.get(c["group"], 0) + 1
    assert groups == {
        "exact": 10,
        "paraphrase": 10,
        "similar_different": 10,
        "unrelated": 10,
    }, groups
    return seeds, cases


def seed_answers(qa, seeds, regen: bool) -> dict:
    if SEED_FILE.exists() and not regen:
        return json.loads(SEED_FILE.read_text())
    log(C, "producing the 10 seed answers with the HW8 agent path (one time)")
    out = {}
    for s in seeds:
        g = qa.facts.ground(s["query"])
        agent = qa.agent.run(s["query"], g.as_prompt())
        out[s["id"]] = {
            "query": s["query"],
            "answer": agent["answer"],
            "data_version": g.data_version,
            "deps": g.deps,
            "facts": g.lines,
            "agent_ms": agent["agent_ms"],
        }
        log(C, f"seed {s['id']} answered in {agent['agent_ms']} ms")
    RAW.mkdir(parents=True, exist_ok=True)
    SEED_FILE.write_text(json.dumps(out, indent=2, default=str))
    return out


def classify(case, res, seed_by_query) -> str:
    matched = seed_by_query.get(res.get("matched_query")) if res["is_cached"] else None
    if case["expected"] == "hit":
        if not res["is_cached"]:
            return "missed_hit"
        return "correct_hit" if matched == case["target"] else "false_hit"
    return "false_hit" if res["is_cached"] else "correct_miss"


def cost(summary: dict, miss_cost: float, false_hit_cost: float) -> float:
    return round(
        summary["misses"] * miss_cost + summary["false_hits"] * false_hit_cost, 2
    )


def run_threshold(qa, threshold, seeds_ans, cases) -> dict:
    qa.cache.threshold = threshold
    qa.cache.backend.flush()
    seed_by_query = {}
    for sid, s in seeds_ans.items():
        vec = qa.embedder.embed(s["query"])
        qa.cache.store(s["query"], vec, s["answer"], s["data_version"], s["deps"])
        seed_by_query[s["query"]] = sid
    log(C, f"threshold={threshold}: cache emptied and 10 seeds stored")

    rows = []
    for case in cases:
        res = qa.ask(case["query"])
        res["matched_seed"] = seed_by_query.get(res.get("matched_query"))
        res["nearest_seed"] = seed_by_query.get(res.get("nearest_query"))
        res["outcome"] = classify(case, res, seed_by_query)
        res["ground_truth_facts"] = qa.facts.ground(case["query"]).lines  # not timed
        res.update({k: case.get(k) for k in ("id", "group", "expected", "target")})
        rows.append(res)
        log(
            C,
            f"{case['id']} {case['group']:<17} expected={case['expected']:<4} "
            f"is_cached={str(res['is_cached']):<5} sim={res['similarity']:.4f} "
            f"nearest={res['nearest_seed']} -> {res['outcome']} "
            f"({res['latency_ms']:.0f} ms)",
        )

    hits = [r for r in rows if r["is_cached"]]
    false_hits = [r for r in rows if r["outcome"] == "false_hit"]
    summary = {
        "threshold": threshold,
        "cases": len(rows),
        "hits": len(hits),
        "misses": len(rows) - len(hits),
        "false_hits": len(false_hits),
        "missed_hits": sum(r["outcome"] == "missed_hit" for r in rows),
        "hit_rate_pct": round(100 * len(hits) / len(rows), 1),
        "false_hit_rate_pct": round(100 * len(false_hits) / len(hits), 1)
        if hits
        else 0.0,
        "mean_latency_ms": round(statistics.mean(r["latency_ms"] for r in rows), 1),
        "mean_latency_hit_ms": round(statistics.mean(r["latency_ms"] for r in hits), 1)
        if hits
        else None,
        "mean_latency_miss_ms": round(
            statistics.mean(r["latency_ms"] for r in rows if not r["is_cached"]), 1
        )
        if len(hits) < len(rows)
        else None,
    }
    return {"summary": summary, "rows": rows}


def print_table(summaries, miss_cost, false_hit_cost):
    print("\n=== Threshold sweep (40 cases) ===")
    print(
        f"cost model: miss = {miss_cost}, false hit = {false_hit_cost} "
        "(see METRICS.md 3.4)"
    )
    head = (
        f"{'Threshold':>9} | {'Hit rate':>8} | {'False-hit rate':>14} | "
        f"{'Mean latency (ms)':>17} | {'Total cost':>10} | hits/false/missed"
    )
    print(head)
    print("-" * len(head))
    for s in summaries:
        print(
            f"{s['threshold']:>9.2f} | {s['hit_rate_pct']:>7.1f}% | "
            f"{s['false_hit_rate_pct']:>13.1f}% | {s['mean_latency_ms']:>17.1f} | "
            f"{cost(s, miss_cost, false_hit_cost):>10.1f} | "
            f"{s['hits']}/{s['false_hits']}/{s['missed_hits']}"
        )


def main(args) -> int:
    banner("part3_threshold_sweep.py (Part 3.2)")
    seeds, cases = load_cases()
    qa = build_qa(
        args.thresholds[0],
        store_on_miss=False,
        agent_mode=args.agent_path,
        llm=args.llm,
        backend=args.backend,
    )
    seeds_ans = seed_answers(qa, seeds, args.regen_seeds)
    summaries = []
    for t in args.thresholds:
        out_file = RAW / f"part3_sweep_{t:.2f}.json"
        if out_file.exists() and not args.force:
            log(C, f"threshold={t}: {out_file.name} exists, skipping (use --force)")
            summaries.append(json.loads(out_file.read_text())["summary"])
            continue
        result = run_threshold(qa, t, seeds_ans, cases)
        out_file.write_text(json.dumps(result, indent=2, default=str))
        log(C, f"saved {out_file}")
        summaries.append(result["summary"])
    print_table(summaries, args.miss_cost, args.false_hit_cost)
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "--thresholds", type=float, nargs="+", default=[0.75, 0.80, 0.85, 0.90, 0.95]
    )
    p.add_argument("--agent-path", choices=["inproc", "kafka"], default="inproc")
    p.add_argument("--llm", choices=["real", "stub"], default="real")
    p.add_argument("--backend", choices=["redis", "memory"], default="redis")
    p.add_argument("--force", action="store_true")
    p.add_argument("--regen-seeds", action="store_true")
    p.add_argument("--miss-cost", type=float, default=1.0)
    p.add_argument("--false-hit-cost", type=float, default=20.0)
    raise SystemExit(main(p.parse_args()))
