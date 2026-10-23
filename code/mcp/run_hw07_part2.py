"""HW7 Part 2 runner.

    python code/mcp/run_hw07_part2.py tasks          # A, B, C + error recovery
    python code/mcp/run_hw07_part2.py reliability    # 21 attempts (7 x A/B/C)

Console output is also appended (timestamped) to reports/hw07/RUN_LOG.txt;
raw data goes to reports/hw07/raw/.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent
CODE_DIR = MCP_DIR.parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != CODE_DIR.resolve()]
sys.path.insert(0, str(MCP_DIR))
os.environ.setdefault("MODEL_MAX_TOKENS", "512")

from agent_loop import LOST_CHAIN, MALFORMED, TEXT_INSTEAD, UNKNOWN_TOOL, run_agent
from hw07_runlog import RAW, header, log, save_json
from hw07_tasks import ERROR_TASK, TASKS, verify, verify_error_recovery

FAILURE_TYPES = [MALFORMED, UNKNOWN_TOOL, TEXT_INSTEAD, LOST_CHAIN]


def run_tasks(model=None) -> int:
    header("HW7 Part 2 - verification tasks A/B/C + error recovery")
    rows = []
    for task_id, task in TASKS.items():
        log(f"\n--- Task {task_id}: {task['name']} ---")
        log(f"prompt: {task['prompt']}")
        run = run_agent(task["prompt"], model=model, temperature=0.0, log=log)
        result = verify(task_id, run)
        log(f"final answer: {run['answer']}")
        log(f"verifier: passed={result['passed']} checks={result['checks']}")
        rows.append({"task": task_id, "run": run, "verifier": result})

    log("\n--- Error recovery: nonexistent incident ---")
    log(f"prompt: {ERROR_TASK['prompt']}")
    run = run_agent(ERROR_TASK["prompt"], model=model, temperature=0.0, log=log)
    check = verify_error_recovery(run)
    log(f"final answer: {run['answer']}")
    log(f"error-recovery check: passed={check['passed']} checks={check['checks']}")
    rows.append({"task": "error_recovery", "run": run, "verifier": check})
    path = save_json("part2_tasks.json", rows)
    log(f"saved {path.relative_to(path.parents[3])}")
    return 0 if all(r["verifier"]["passed"] for r in rows) else 1


def run_reliability(attempts: int, temperature: float, model=None) -> int:
    header(
        f"HW7 Part 2 - reliability: {attempts} attempts over tasks A/B/C, "
        f"temperature={temperature}, max_iterations=8, max_repairs=2"
    )
    task_ids = list(TASKS)
    records = []
    for index in range(attempts):
        task_id = task_ids[index % len(task_ids)]
        log(f"\n--- attempt {index + 1}/{attempts} task {task_id} ---")
        run = run_agent(
            TASKS[task_id]["prompt"], model=model, temperature=temperature, log=log
        )
        result = verify(task_id, run)
        failure_counts = Counter(f["type"] for f in run["failures"])
        if not result["checks"]["tool_chain_complete"]:
            failure_counts[LOST_CHAIN] += 1
        opportunities = run["proposed_calls"] + failure_counts[TEXT_INSTEAD]
        record = {
            "attempt": index + 1,
            "task": task_id,
            "temperature": temperature,
            "stop_reason": run["stop_reason"],
            "tool_use_opportunities": opportunities,
            "proposed_calls": run["proposed_calls"],
            "well_formed_first_try": run["well_formed_first_try"],
            "repaired_ok": run["repaired_ok"],
            "repairs_used": run["repairs_used"],
            "executed_tool_calls": run["tool_calls"],
            **{f"fail_{name}": failure_counts[name] for name in FAILURE_TYPES},
            "attempt_clean_before_repair": sum(
                failure_counts[n] for n in (MALFORMED, UNKNOWN_TOOL, TEXT_INSTEAD)
            )
            == 0,
            "attempt_well_formed_after_repair": run["stop_reason"] == "final_answer"
            and result["checks"]["tool_chain_complete"],
            "verifier_passed": result["passed"],
            "tokens": run["tokens"],
            "latency_ms": run["latency_ms"],
            "run_id": run["run_id"],
        }
        records.append(record)
        log(
            f"result: stop={record['stop_reason']} passed={record['verifier_passed']} "
            f"failures={dict(failure_counts)}"
        )

    RAW.mkdir(parents=True, exist_ok=True)
    csv_path = RAW / "reliability_attempts.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

    total_opp = sum(r["tool_use_opportunities"] for r in records) or 1
    first = sum(r["well_formed_first_try"] for r in records)
    repaired = sum(r["repaired_ok"] for r in records)
    summary = {
        "attempts": attempts,
        "temperature": temperature,
        "tool_use_opportunities": total_opp,
        "call_well_formed_rate_before_repair": round(first / total_opp, 3),
        "call_well_formed_rate_after_repair": round((first + repaired) / total_opp, 3),
        "attempt_clean_rate_before_repair": round(
            sum(r["attempt_clean_before_repair"] for r in records) / attempts, 3
        ),
        "attempt_well_formed_rate_after_repair": round(
            sum(r["attempt_well_formed_after_repair"] for r in records) / attempts, 3
        ),
        "task_success_rate": round(
            sum(r["verifier_passed"] for r in records) / attempts, 3
        ),
        "failures_by_type": {
            name: sum(r[f"fail_{name}"] for r in records) for name in FAILURE_TYPES
        },
        "attempts_with_failure_by_type": {
            name: sum(1 for r in records if r[f"fail_{name}"]) for name in FAILURE_TYPES
        },
    }
    save_json("reliability_summary.json", summary)
    log("\nRELIABILITY SUMMARY")
    for key, value in summary.items():
        log(f"  {key}: {value}")
    log(f"raw per-attempt data: {csv_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["tasks", "reliability"])
    parser.add_argument("--attempts", type=int, default=21)
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="same setting for every reliability attempt (0.0 makes them identical)",
    )
    args = parser.parse_args()
    if args.mode == "tasks":
        return run_tasks()
    return run_reliability(args.attempts, args.temperature)


if __name__ == "__main__":
    raise SystemExit(main())
