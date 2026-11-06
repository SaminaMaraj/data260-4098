"""HW9 Part 1: Redis view counter for one incident.

    python code/hw9/part1_view_counter.py              # 25 accesses of INC-000042
    python code/hw9/part1_view_counter.py --code INC-000100 --accesses 25

Resets the Redis key and the DB column for the chosen incident first, so the
output starts at 1. At the end it prints Redis vs DB values and a small timing
comparison (Redis INCR path vs. writing the DB on every view).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from src.hw9_cache.config import banner  # noqa: E402
from src.hw9_cache.db import (  # noqa: E402
    ensure_view_count_column,
    get_engine,
    get_redis,
)
from src.hw9_cache.views import IncidentStoreWithCache  # noqa: E402

RAW = ROOT / "reports" / "hw09" / "raw"


def main(args) -> int:
    banner("part1_view_counter.py (Part 1)")
    engine = get_engine()
    if ensure_view_count_column(engine):
        print("Added column incidents.view_count (INT NOT NULL DEFAULT 0)")
    r = get_redis()
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT id, incident_code, incident_title FROM incidents "
                    "WHERE incident_code = :c"
                ),
                {"c": args.code},
            )
            .mappings()
            .first()
        )
    if row is None:
        print(f"Incident {args.code} not found in s4098_rel")
        return 1
    incident_id = int(row["id"])
    # verbose=False: the method's sync message is printed below, after the
    # "Access #n" line, so the output reads in the same order as the assignment
    store = IncidentStoreWithCache(engine, r, verbose=False)
    store.reset(incident_id)
    print(
        f"Incident {row['incident_code']} (id={incident_id}): {row['incident_title']}"
    )
    print(f"Redis key: {store.views_key(incident_id)}")

    print("\n=== Testing Counter ===\n")
    latencies = []
    totals = []
    for i in range(1, args.accesses + 1):
        t0 = time.perf_counter()
        total = store.increment_incident_views(incident_id)
        latencies.append((time.perf_counter() - t0) * 1000)
        totals.append(total)
        print(f"Access #{i}: Total = {total}")
        if store.last_synced == total:
            print(
                "✓ Synced views to database"
                f"   (UPDATE incidents SET view_count={total} WHERE id={incident_id})"
            )

    redis_value = int(r.get(store.views_key(incident_id)))
    db_value = store.db_view_count(incident_id)
    print("\n=== After the run ===")
    print(f"Redis {store.views_key(incident_id)} = {redis_value}")
    print(f"s4098_rel incidents.view_count (id={incident_id}) = {db_value}")
    print(f"DB writes: {store.db_writes} for {args.accesses} views")

    # timing comparison on a second incident so the demo row is not touched
    print(f"\n=== Timing: {args.timing_runs} views, Redis path vs DB on every view ===")
    other_id = incident_id + 1
    timing_store = IncidentStoreWithCache(engine, r, verbose=False)
    timing_store.reset(other_id)
    redis_ms, db_ms = [], []
    for _ in range(args.timing_runs):
        t0 = time.perf_counter()
        timing_store.increment_incident_views(other_id)
        redis_ms.append((time.perf_counter() - t0) * 1000)
    for _ in range(args.timing_runs):
        t0 = time.perf_counter()
        timing_store.increment_views_db_only(other_id)
        db_ms.append((time.perf_counter() - t0) * 1000)
    timing_store.reset(other_id)
    timing = {
        "redis_counter_ms_mean": round(statistics.mean(redis_ms), 3),
        "redis_counter_ms_p50": round(statistics.median(redis_ms), 3),
        "db_every_view_ms_mean": round(statistics.mean(db_ms), 3),
        "db_every_view_ms_p50": round(statistics.median(db_ms), 3),
        "runs": args.timing_runs,
    }
    print(
        f"Redis INCR (+ DB write every 10th): mean {timing['redis_counter_ms_mean']} ms"
        f", p50 {timing['redis_counter_ms_p50']} ms"
    )
    print(
        f"DB UPDATE + SELECT every view:      mean {timing['db_every_view_ms_mean']} ms"
        f", p50 {timing['db_every_view_ms_p50']} ms"
    )

    RAW.mkdir(parents=True, exist_ok=True)
    out = {
        "incident_code": args.code,
        "incident_id": incident_id,
        "redis_key": store.views_key(incident_id),
        "totals": totals,
        "latency_ms": [round(x, 3) for x in latencies],
        "redis_value": redis_value,
        "db_value": db_value,
        "db_writes": store.db_writes,
        "timing": timing,
    }
    (RAW / "part1_counter.json").write_text(json.dumps(out, indent=2))
    print(f"\nsaved {RAW / 'part1_counter.json'}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--code", default="INC-000042")
    p.add_argument("--accesses", type=int, default=25)
    p.add_argument("--timing-runs", type=int, default=200)
    raise SystemExit(main(p.parse_args()))
