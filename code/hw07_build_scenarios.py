"""Build the two HW7 Part 4 scenarios from REAL Bay Wheels trip data.

1. Download one monthly file from https://s3.amazonaws.com/baywheels-data/index.html
   (e.g. 202509-baywheels-tripdata.csv.zip) into data/ (git-ignored).
2. python code/hw07_build_scenarios.py data/202509-baywheels-tripdata.csv.zip

Public trip data has no rider identity, so each scenario assigns a synthetic
rider_id (seeded with SEED=4098) to otherwise unmodified real trip rows:

  A  membership should win : 600 real trips of 8-60 min (classic + ebike)
                             spread over 15 riders  -> ~40 rides per rider-month
  B  pay-per-use should win: 520 real classic trips of <= 12 min
                             spread over 260 riders -> ~2 rides per rider-month

Outputs (reports/hw07/raw/scenarios/):
  scenario_A_membership.csv, scenario_B_payg.csv, scenario_summaries.json
"""

from __future__ import annotations

import csv
import io
import json
import random
import statistics
import sys
import zipfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "reports" / "hw07" / "raw" / "scenarios"
SEED = 4098
KEEP = [
    "ride_id",
    "rideable_type",
    "started_at",
    "ended_at",
    "start_station_name",
    "end_station_name",
    "member_casual",
]


def read_rows(path: Path) -> list[dict[str, str]]:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            name = next(
                n
                for n in archive.namelist()
                if n.endswith(".csv") and not n.startswith("__MACOSX")
            )
            text = archive.read(name).decode("utf-8-sig")
    else:
        text = path.read_text(encoding="utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def minutes(row: dict[str, str]) -> float | None:
    try:
        start = datetime.fromisoformat(row["started_at"])
        end = datetime.fromisoformat(row["ended_at"])
    except (KeyError, ValueError):
        return None
    value = (end - start).total_seconds() / 60
    return value if 0 < value < 24 * 60 else None


def build(rows, predicate, size, riders, label, rng):
    pool = [r for r in rows if predicate(r)]
    if len(pool) < size:
        raise SystemExit(f"{label}: only {len(pool)} matching trips (need {size})")
    sample = rng.sample(pool, size)
    sample.sort(key=lambda r: r["started_at"])
    order = list(range(size))
    rng.shuffle(order)
    out = []
    for position, index in enumerate(order):
        row = {k: sample[index].get(k, "") for k in KEEP}
        row["rider_id"] = f"{label}-rider-{position % riders + 1:03d}"
        out.append(row)
    out.sort(key=lambda r: r["started_at"])
    return out, len(pool)


def summarize(rows, pool_size, source, rule):
    durations = [minutes(r) for r in rows]
    return {
        "source_file": source,
        "selection_rule": rule,
        "matching_trips_in_source": pool_size,
        "rows": len(rows),
        "riders_synthetic": len({r["rider_id"] for r in rows}),
        "ebike_rides": sum("electric" in r["rideable_type"] for r in rows),
        "classic_rides": sum("classic" in r["rideable_type"] for r in rows),
        "duration_min_mean": round(statistics.mean(durations), 2),
        "duration_min_median": round(statistics.median(durations), 2),
        "first_start": rows[0]["started_at"],
        "last_start": rows[-1]["started_at"],
        "member_casual_counts": {
            v: sum(r["member_casual"] == v for r in rows)
            for v in sorted({r["member_casual"] for r in rows})
        },
    }


def write(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=KEEP + ["rider_id"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    source = Path(sys.argv[1])
    rows = read_rows(source)
    print(f"Kazi Samina Maraj Mumu | read {len(rows)} trips from {source.name}")
    rng = random.Random(SEED)

    rule_a = "8 <= duration <= 60 min, any bike type; 600 trips over 15 riders"
    a_rows, a_pool = build(
        rows,
        lambda r: (m := minutes(r)) is not None and 8 <= m <= 60,
        600,
        15,
        "A",
        rng,
    )
    rule_b = "classic_bike, duration <= 12 min; 520 trips over 260 riders"
    b_rows, b_pool = build(
        rows,
        lambda r: (
            r.get("rideable_type") == "classic_bike"
            and (m := minutes(r)) is not None
            and m <= 12
        ),
        520,
        260,
        "B",
        rng,
    )
    write(a_rows, OUT / "scenario_A_membership.csv")
    write(b_rows, OUT / "scenario_B_payg.csv")
    summaries = {
        "seed": SEED,
        "note": "rider_id is synthetic; all other columns are unmodified public rows",
        "A_membership": summarize(a_rows, a_pool, source.name, rule_a),
        "B_payg": summarize(b_rows, b_pool, source.name, rule_b),
    }
    (OUT / "scenario_summaries.json").write_text(
        json.dumps(summaries, indent=2), encoding="utf-8"
    )
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
