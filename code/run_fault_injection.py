"""Run the required 150-call seeded fault-injection experiment."""

from __future__ import annotations

import csv
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path[:] = [x for x in sys.path if Path(x or '.').resolve() != Path(__file__).resolve().parent]
MCP_DIR = REPO_ROOT / "code" / "mcp"
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(MCP_DIR))

import transit_server as transit


VERIFY_SEED = 264098
FAILURE_RATES = [0.0, 0.20, 0.50]
CALLS_PER_RATE = 50
OUTPUT_PATH = REPO_ROOT / "reports" / "hw05" / "raw" / "fault_injection.csv"


def p99(values: list[float]) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(0.99 * len(ordered)) - 1)
    return ordered[index]


def run_rate(rate: float) -> list[dict[str, object]]:
    transit.configure_fault_injection(rate, seed=VERIFY_SEED)
    rows = []

    for call_idx in range(1, CALLS_PER_RATE + 1):
        started = time.perf_counter()
        result = transit.search_incidents(
            query="delay",
            category="delay",
            limit=1,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        rows.append(
            {
                "rate": rate,
                "call_idx": call_idx,
                "attempts": transit.last_retry_attempts,
                "success": bool(result.get("ok")),
                "latency_ms": round(latency_ms, 3),
                "error": result.get("error") or "",
            }
        )

    return rows


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    all_rows = []

    for rate in FAILURE_RATES:
        all_rows.extend(run_rate(rate))

    with OUTPUT_PATH.open("w", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "rate",
                "call_idx",
                "attempts",
                "success",
                "latency_ms",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"timestamp_utc={datetime.now(timezone.utc).isoformat()}")
    print(f"wrote={OUTPUT_PATH}")
    print(f"total_calls={len(all_rows)}")

    for rate in FAILURE_RATES:
        rows = [row for row in all_rows if row["rate"] == rate]
        successes = sum(bool(row["success"]) for row in rows)
        latencies = [float(row["latency_ms"]) for row in rows]
        print(
            f"rate={rate:.0%} calls={len(rows)} "
            f"success_rate={successes / len(rows):.3f} "
            f"mean_latency_ms={sum(latencies) / len(latencies):.3f} "
            f"p99_latency_ms={p99(latencies):.3f}"
        )


if __name__ == "__main__":
    main()
