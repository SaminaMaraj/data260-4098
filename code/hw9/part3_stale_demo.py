"""HW9 Part 3.5: stale cached answer and data-version invalidation.

    python code/hw9/part3_stale_demo.py            # runs all steps, restores the record at the end
    python code/hw9/part3_stale_demo.py --keep     # leave the updated record in s4098_rel

Steps
  1. empty the cache, ask "Who operates VTA Route 522?" -> miss, agent answer is
     stored with deps={routes:[RT-003]} and data_version = hash of that route row
  2. UPDATE routes SET operator=... WHERE route_name='VTA Route 522'   (s4098_rel)
  3. invalidation=none:    same question -> HIT, returns the OLD operator (stale hit)
  4. invalidation=version: same question -> data_version mismatch -> entry deleted,
     agent re-runs with the new record, new answer + new data_version stored
  5. ask again -> HIT with the fresh answer
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sqlalchemy import text  # noqa: E402

from src.hw9_cache.config import DEFAULT_THRESHOLD, banner  # noqa: E402
from src.hw9_cache.qa import build_qa  # noqa: E402

RAW = ROOT / "reports" / "hw09" / "raw"
ROUTE_NAME = "VTA Route 522"  # looked up by name: route codes differ per database
FIRST_Q = "Who operates VTA Route 522?"
NEW_OPERATOR = "MV Transportation (VTA contract)"


def route_row(engine) -> dict:
    with engine.connect() as conn:
        return dict(
            conn.execute(
                text(
                    "SELECT id, route_code, route_name, operator FROM routes "
                    "WHERE route_name = :n"
                ),
                {"n": ROUTE_NAME},
            )
            .mappings()
            .one()
        )


def set_operator(engine, operator: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE routes SET operator = :o WHERE route_name = :n"),
            {"o": operator, "n": ROUTE_NAME},
        )


def show(step: str, res: dict) -> dict:
    print(
        f"    is_cached={res['is_cached']}  similarity={res['similarity']:.4f}  "
        f"invalidated={res['invalidated']}  data_version={res.get('data_version')}  "
        f"latency={res['latency_ms']:.1f} ms"
    )
    print(f"    answer: {' '.join(str(res['answer']).split())}\n")
    return {
        "step": step,
        **{
            k: res.get(k)
            for k in (
                "question",
                "is_cached",
                "similarity",
                "invalidated",
                "stale_data_version",
                "data_version",
                "deps",
                "answer",
                "latency_ms",
                "matched_query",
            )
        },
    }


def main(args) -> int:
    banner("part3_stale_demo.py (Part 3.5)")
    qa = build_qa(
        args.threshold,
        invalidation="version",
        agent_mode=args.agent_path,
        llm=args.llm,
        backend=args.backend,
    )
    engine = qa.facts.engine
    original = route_row(engine)
    if original["operator"] != args.original_operator:
        print(
            f"note: operator is '{original['operator']}', resetting to "
            f"'{args.original_operator}' for a clean start"
        )
        set_operator(engine, args.original_operator)
        original = route_row(engine)
    qa.cache.backend.flush()
    log = []

    print(f"\n[1] s4098_rel record before: {original}")
    print(f"[1] ask (cache empty): {FIRST_Q}")
    log.append(show("1 first ask, miss -> stored", qa.ask(FIRST_Q)))

    print(
        f"[2] UPDATE routes SET operator='{NEW_OPERATOR}' "
        f"WHERE route_name='{ROUTE_NAME}'   (route_code {original['route_code']})"
    )
    set_operator(engine, NEW_OPERATOR)
    updated = route_row(engine)
    print(f"[2] s4098_rel record after:  {updated}\n")

    print(f"[3] invalidation=none  ask: {FIRST_Q}")
    qa.invalidation = "none"
    stale = qa.ask(FIRST_Q)
    log.append(show("3 stale hit (no invalidation)", stale))
    print(
        f"    -> STALE: cached answer was produced when operator='{original['operator']}',"
        f" database now says '{updated['operator']}'\n"
    )

    print(f"[4] invalidation=version  ask: {FIRST_Q}")
    qa.invalidation = "version"
    fresh = qa.ask(FIRST_Q)
    log.append(show("4 version check -> invalidated -> recomputed", fresh))

    print(f"[5] invalidation=version  ask again: {FIRST_Q}")
    log.append(show("5 hit with the fresh answer", qa.ask(FIRST_Q)))

    if not args.keep:
        set_operator(engine, original["operator"])
        print(
            f"restored operator='{original['operator']}' for {original['route_code']}"
        )

    RAW.mkdir(parents=True, exist_ok=True)
    out = {"route_before": original, "route_after": updated, "steps": log}
    (RAW / "part3_stale_demo.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"saved {RAW / 'part3_stale_demo.json'}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    p.add_argument("--original-operator", default="VTA")
    p.add_argument("--agent-path", choices=["inproc", "kafka"], default="inproc")
    p.add_argument("--llm", choices=["real", "stub"], default="real")
    p.add_argument("--backend", choices=["redis", "memory"], default="redis")
    p.add_argument("--keep", action="store_true")
    raise SystemExit(main(p.parse_args()))
