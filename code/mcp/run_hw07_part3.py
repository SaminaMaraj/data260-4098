"""HW7 Part 3 runner: original loop vs Reflexion loop on the same fixed tasks.

    python code/mcp/run_hw07_part3.py --repeats 3 --temperature 0.7

Writes reports/hw07/raw/reflexion_comparison.csv, reflexion_summary.json and
(on any failure) reflections.jsonl.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent
CODE_DIR = MCP_DIR.parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != CODE_DIR.resolve()]
sys.path.insert(0, str(MCP_DIR))
os.environ.setdefault("MODEL_MAX_TOKENS", "512")

from agent_loop import run_agent
from hw07_runlog import RAW, header, log, save_json
from hw07_tasks import TASKS, ground_truth, verify
from reflexion import TOKEN_BUDGET, TOOL_BUDGET, run_reflexion


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument(
        "--prompts",
        choices=["explicit", "vague"],
        default="explicit",
        help="explicit = tools named in the prompt; vague = same task, no tool hints",
    )
    args = parser.parse_args()
    key = "prompt" if args.prompts == "explicit" else "vague_prompt"
    suffix = "" if args.prompts == "explicit" else "_vague"
    header(
        f"HW7 Part 3 - original vs Reflexion, prompts={args.prompts}, "
        f"repeats={args.repeats}, "
        f"temperature={args.temperature}, tool_budget={TOOL_BUDGET}, "
        f"token_budget={TOKEN_BUDGET}, max_retries=2"
    )
    rows = []
    for repeat in range(1, args.repeats + 1):
        for task_id in TASKS:
            truth = ground_truth(task_id)
            log(f"\n=== repeat {repeat} task {task_id} | ORIGINAL loop ===")
            run = run_agent(TASKS[task_id][key], temperature=args.temperature, log=log)
            result = verify(task_id, run, truth)
            log(f"answer: {run['answer']}")
            log(
                f"verifier: passed={result['passed']} "
                f"failed={result['failed_assertions']}"
            )
            rows.append(
                {
                    "loop": "original",
                    "prompts": args.prompts,
                    "repeat": repeat,
                    "task": task_id,
                    "success": result["passed"],
                    "stop_reason": run["stop_reason"],
                    "unsupported_claims": len(result["unsupported_claims"]),
                    "retries": 0,
                    "tool_calls": run["tool_calls"],
                    "tokens": run["tokens"],
                    "latency_ms": run["latency_ms"],
                    "verifier_false_rejection": result["false_rejection_candidate"],
                    "run_id": run["run_id"],
                }
            )

            log(f"\n=== repeat {repeat} task {task_id} | REFLEXION loop ===")
            out = run_reflexion(
                task_id, temperature=args.temperature, prompt_key=key, log=log
            )
            final = out["final"]
            log(f"answer: {out['answer']}")
            log(f"stop_reason={out['stop_reason']} retries={out['retries']}")
            rows.append(
                {
                    "loop": "reflexion",
                    "prompts": args.prompts,
                    "repeat": repeat,
                    "task": task_id,
                    "success": out["stop_reason"] == "success",
                    "stop_reason": out["stop_reason"],
                    "unsupported_claims": len(final.get("unsupported_claims", [])),
                    "retries": out["retries"],
                    "tool_calls": out["tool_calls"],
                    "tokens": out["tokens"],
                    "latency_ms": out["latency_ms"],
                    "verifier_false_rejection": any(
                        a["verifier"]["false_rejection_candidate"]
                        for a in out["attempts"]
                    ),
                    "run_id": out["run_id"],
                }
            )

    RAW.mkdir(parents=True, exist_ok=True)
    with (RAW / f"reflexion_comparison{suffix}.csv").open(
        "w", newline="", encoding="utf-8"
    ) as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {}
    for loop in ("original", "reflexion"):
        group = [r for r in rows if r["loop"] == loop]
        n = len(group)
        summary[loop] = {
            "runs": n,
            "task_success": f"{sum(r['success'] for r in group)}/{n}",
            "unsupported_claims": sum(r["unsupported_claims"] for r in group),
            "retry_rate": round(sum(r["retries"] > 0 for r in group) / n, 3),
            "mean_tool_calls": round(sum(r["tool_calls"] for r in group) / n, 2),
            "mean_tokens": round(sum(r["tokens"] for r in group) / n, 1),
            "mean_latency_ms": round(sum(r["latency_ms"] for r in group) / n, 1),
            "verifier_false_rejections": sum(
                r["verifier_false_rejection"] for r in group
            ),
            "stop_reasons": {
                s: sum(r["stop_reason"] == s for r in group)
                for s in sorted({r["stop_reason"] for r in group})
            },
        }
    save_json(f"reflexion_summary{suffix}.json", summary)
    log("\n| Metric | Original loop | Reflexion loop |")
    log("|---|---|---|")
    labels = [
        ("Task success", "task_success"),
        ("Unsupported claims", "unsupported_claims"),
        ("Retry rate", "retry_rate"),
        ("Tool calls (mean)", "mean_tool_calls"),
        ("Tokens (mean)", "mean_tokens"),
        ("Latency (ms, mean)", "mean_latency_ms"),
        ("Verifier false rejections", "verifier_false_rejections"),
    ]
    for label, key in labels:
        log(f"| {label} | {summary['original'][key]} | {summary['reflexion'][key]} |")
    log(
        "NOTE: verifier false rejections are candidates (strict check failed, relaxed "
        "check passed). Open the rows in reflexion_comparison.csv and confirm by hand."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
