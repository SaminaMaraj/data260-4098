"""Build reports/hw09/METRICS.md from reports/hw09/raw/*.json.

    python code/hw9/build_metrics.py [--miss-cost 1 --false-hit-cost 20]

Every number in METRICS.md is read from the raw files written by the HW9 scripts.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.hw9_agents.reference import DATA_DIR  # noqa: E402
from src.hw9_cache.config import PREFIX, STUDENT_NAME  # noqa: E402

RAW = ROOT / "reports" / "hw09" / "raw"
OUT = ROOT / "reports" / "hw09" / "METRICS.md"
THRESHOLDS = [0.75, 0.80, 0.85, 0.90, 0.95]


def load(name):
    p = RAW / name
    return json.loads(p.read_text()) if p.exists() else None


def one_line(text, n=400):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 3] + "..."


def part1(md):
    d = load("part1_counter.json")
    md.append("## Part 1 - Redis view counter\n")
    if not d:
        md.append("_not run yet_\n")
        return
    t = d["timing"]
    md += [
        f"- Incident `{d['incident_code']}` (id {d['incident_id']}), key `{d['redis_key']}`",
        f"- {len(d['totals'])} accesses -> Redis = **{d['redis_value']}**, "
        f"incidents.view_count = **{d['db_value']}** ({d['db_writes']} DB writes, at 10 and 20)",
        "",
        "| Path | mean ms | p50 ms |",
        "|---|---:|---:|",
        f"| Redis INCR (+ DB write every 10th) | {t['redis_counter_ms_mean']} | {t['redis_counter_ms_p50']} |",
        f"| DB UPDATE + SELECT on every view | {t['db_every_view_ms_mean']} | {t['db_every_view_ms_p50']} |",
        f"\n({t['runs']} views per path)\n",
    ]


def part2(md):
    d = load("part2_results.json")
    md.append("## Part 2 - Semantic cache (threshold 0.85)\n")
    if not d:
        md.append("_not run yet_\n")
        return
    s = d["summary"]
    md += [
        f"Embedder `{s['embedder']}`, agent path `{s['agent_path']}`.\n",
        "| # | kind | is_cached | similarity | latency ms |",
        "|---:|---|---|---:|---:|",
    ]
    for r in d["rows"]:
        md.append(
            f"| {r['n']} | {r['kind']} | {r['is_cached']} | {r['similarity']:.4f} | "
            f"{r['latency_ms']:.1f} |"
        )
    md += [
        "",
        f"- Hit rate: **{s['hits']}/{s['queries']} = {s['hit_rate_pct']}%**",
        f"- Average latency cached: **{s['avg_latency_cached_ms']} ms**; "
        f"non-cached: **{s['avg_latency_uncached_ms']} ms**",
        "",
    ]


def sweep():
    out = {}
    for t in THRESHOLDS:
        d = load(f"part3_sweep_{t:.2f}.json")
        if d:
            out[t] = d
    return out


def cost(s, mc, fc):
    return round(s["misses"] * mc + s["false_hits"] * fc, 1)


def part3(md, mc, fc):
    runs = sweep()
    md.append("## Part 3.2 - Threshold sweep (40 labeled cases)\n")
    if not runs:
        md.append("_not run yet_\n")
        return
    md += [
        "False-hit rate = false hits / hits. Total cost = misses x "
        f"{mc} + false hits x {fc}.\n",
        "| Threshold | Hit rate | False-hit rate | Mean latency (ms) | Total cost | hits | false hits | missed should-hits |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for t, d in runs.items():
        s = d["summary"]
        md.append(
            f"| {t:.2f} | {s['hit_rate_pct']}% | {s['false_hit_rate_pct']}% | "
            f"{s['mean_latency_ms']} | {cost(s, mc, fc)} | {s['hits']} | "
            f"{s['false_hits']} | {s['missed_hits']} |"
        )
    md.append("")
    md.append("Per-group hits (hits / 10):\n")
    md.append("| Threshold | exact | paraphrase | similar_different | unrelated |")
    md.append("|---:|---:|---:|---:|---:|")
    for t, d in runs.items():
        g = {}
        for r in d["rows"]:
            g[r["group"]] = g.get(r["group"], 0) + int(r["is_cached"])
        md.append(
            f"| {t:.2f} | {g.get('exact', 0)} | {g.get('paraphrase', 0)} | "
            f"{g.get('similar_different', 0)} | {g.get('unrelated', 0)} |"
        )
    md.append("")

    # 3.3 one false hit in full
    md.append("## Part 3.3 - One false hit in full\n")
    order = [0.85] + [t for t in THRESHOLDS if t != 0.85]
    pick = None
    for t in order:
        if t not in runs:
            continue
        fh = [r for r in runs[t]["rows"] if r["outcome"] == "false_hit"]
        if fh:
            pick = (t, max(fh, key=lambda r: r["similarity"]))
            break
    if not pick:
        md.append("No false hit at any threshold.\n")
    else:
        t, r = pick
        correct = None
        for d in runs.values():
            for x in d["rows"]:
                if x["id"] == r["id"] and not x["is_cached"]:
                    correct = x["answer"]
        md += [
            f"- Threshold: {t:.2f}, case `{r['id']}` ({r['group']})",
            f'- Cached query: "{r["matched_query"]}" (seed {r["matched_seed"]})',
            f'- Incoming query: "{r["question"]}"',
            f"- Similarity: **{r['similarity']:.4f}**",
            f"- Cached answer returned: {one_line(r['answer'])}",
            f"- Correct answer (agent answer for the incoming query, from a threshold where it missed): "
            f"{one_line(correct) if correct else '_never missed_'}",
            f"- Ground truth from s4098_rel: {' '.join(r['ground_truth_facts'])}",
            "",
        ]

    # 3.4
    md.append("## Part 3.4 - Cost per threshold\n")
    best = min(runs.items(), key=lambda kv: (cost(kv[1]["summary"], mc, fc), -kv[0]))
    md.append("| Threshold | misses | false hits | total cost |")
    md.append("|---:|---:|---:|---:|")
    for t, d in runs.items():
        s = d["summary"]
        md.append(
            f"| {t:.2f} | {s['misses']} | {s['false_hits']} | {cost(s, mc, fc)} |"
        )
    md.append(f"\nLowest total cost: **{best[0]:.2f}**\n")

    # 3.5
    d = load("part3_stale_demo.json")
    md.append("## Part 3.5 - Stale answer and invalidation\n")
    if not d:
        md.append("_not run yet_\n")
        return
    md.append(
        f"Record before: `{d['route_before']}`  \nRecord after: `{d['route_after']}`\n"
    )
    md.append("| step | is_cached | invalidated | data_version | latency ms | answer |")
    md.append("|---|---|---|---|---:|---|")
    for s in d["steps"]:
        md.append(
            f"| {s['step']} | {s['is_cached']} | {s['invalidated']} | "
            f"{s['data_version']} | {s['latency_ms']:.1f} | {one_line(s['answer'], 160)} |"
        )
    md.append("")


def part4(md):
    md.append("## Part 4 - Self-improving two-agent system\n")
    demo = load("part4_revision_demo.json")
    if demo:
        md.append("### 4.1 Controlled revision case\n")
        md.append(f"Question: {demo['question']}\n")
        for a in demo["attempts"]:
            ev = a["evaluation"]
            md.append(
                f"- Attempt {a['attempt']}: {one_line(a['answer'], 300)}  \n"
                f"  Evaluator: **{ev['result']}** ({ev['failure_type']}) - "
                f"{ev['explanation']}"
                + (f"  \n  Feedback: {ev['feedback']}" if ev["feedback"] else "")
            )
        md.append(
            f"\nAttempts: {demo['n_attempts']}, final: **{demo['final_result']}**\n"
        )
    lessons = json.loads((DATA_DIR / "lessons.json").read_text())
    if lessons:
        md.append("### Lessons (lessons.json)\n")
        md.append(
            "| lesson_id | failure_type | status | use_count | from | correction |"
        )
        md.append("|---|---|---|---:|---|---|")
        for x in lessons:
            md.append(
                f"| {x['lesson_id']} | {x['failure_type']} | {x['status']} | "
                f"{x['use_count']} | {', '.join(x['source_questions'])} | "
                f"{one_line(x['correction'], 200)} |"
            )
        md.append("")
    val = load("part4_validation.json")
    if val:
        md.append("### 4.3 Validation gate\n")
        md.append(
            "| lesson | first-attempt failures before -> after | regressions | unsupported out-of-scope before -> after | decision |"
        )
        md.append("|---|---|---|---|---|")
        for x in val["lessons"]:
            v = x["verdict"]
            md.append(
                f"| {x['lesson_id']} | {v['first_attempt_failures_before']} -> "
                f"{v['first_attempt_failures_after']} | {v['regressions'] or 'none'} | "
                f"{v['out_of_scope_unsupported_before']} -> "
                f"{v['out_of_scope_unsupported_after']} | "
                f"{'KEEP' if v['keep'] else 'REJECT'} |"
            )
        md.append("")
    test = load("part4_test.json")
    if test:
        md.append("### 4.4 Test results (test_data.json)\n")
        md.append(
            "| Variant | Correct answers | Incorrect answers | Average attempts | Average latency (ms) |"
        )
        md.append("|---|---:|---:|---:|---:|")
        for name, d in test.items():
            s = d["summary"]
            md.append(
                f"| {name} | {s['correct']} | {s['incorrect']} | "
                f"{s['avg_attempts']:.2f} | {s['avg_latency_ms']:.1f} |"
            )
        md.append("")


def main(args):
    md = [
        f"# HW9 Metrics - {STUDENT_NAME}\n",
        f"Generated by `python code/hw9/build_metrics.py` from `reports/hw09/raw/` "
        f"(PREFIX {PREFIX}).\n",
    ]
    part1(md)
    part2(md)
    part3(md, args.miss_cost, args.false_hit_cost)
    part4(md)
    OUT.write_text("\n".join(md) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--miss-cost", type=float, default=1.0)
    p.add_argument("--false-hit-cost", type=float, default=20.0)
    main(p.parse_args())
