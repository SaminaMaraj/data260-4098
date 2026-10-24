"""HW7 Part 4 headless runner (same agent as the UI, plus RUN_LOG output).

S=reports/hw07/raw/scenarios
python code/run_hw07_bikeshare.py $S/scenario_A_membership.csv --label scenario_A
python code/run_hw07_bikeshare.py $S/scenario_B_payg.csv --label scenario_B
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = REPO_ROOT / "code"
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != CODE_DIR.resolve()]
sys.path.insert(0, str(REPO_ROOT))

from src.hw7_bikeshare_agent import DEFAULT_PRICING_URL, run_bikeshare_agent
from src.hw7_runlog import RAW, header, log


def log_result(result: dict) -> None:
    for index, step in enumerate(result["timeline"], start=1):
        if step["type"] == "tool_call":
            log(
                f"  step {index}: CALL {step['tool']} {json.dumps(step['input'])[:300]}"
            )
        elif step["type"] == "feedback":
            log(f"  step {index}: FEEDBACK {step['text'][:400]}")
        else:
            out = step["output"]
            status = "ok" if out.get("success") else f"error={out.get('error')}"
            log(f"  step {index}: OBS  {step['tool']} {status}")
    final = result["final"]
    log(f"decision: {result['decision']}")
    log(
        f"pay_per_use_total={final.get('pay_per_use_total')} "
        f"membership_fees={final.get('membership_fees')} "
        f"member_residual={final.get('member_residual')} "
        f"membership_total={final.get('membership_total')} "
        f"break_even={final.get('break_even_rides_per_rider_month')} "
        f"actual={final.get('actual_rides_per_rider_month')}"
    )
    log(f"justification: {final.get('justification', result['final_text'][:400])}")
    for rnd in result["validation"]["rounds"]:
        failed = [c["check"] for c in rnd["checks"] if not c["ok"]]
        log(f"validation round {rnd['round']}: passed={rnd['passed']} failed={failed}")
    log(f"validated={result['validated']}")
    for cite in result["citations"]:
        log(
            f"citation: {cite['url']} {cite['snapshot_mode']} "
            f"captured={cite['captured_at']} "
            f"sha256={cite['sha256']}"
        )
    log(f"metrics: {json.dumps(result['metrics'])}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--url", default=DEFAULT_PRICING_URL)
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--reuse-snapshot",
        type=Path,
        help="saved pricing_snapshot.json to reuse instead of fetching the page",
    )
    args = parser.parse_args()
    header(f"HW7 Part 4 - Bay Wheels agent run '{args.label}' on {args.csv.name}")
    out_dir = RAW / "bikeshare" / args.label
    result = run_bikeshare_agent(
        args.csv.read_bytes(),
        args.url,
        snapshot_dir=out_dir,
        reuse_snapshot=args.reuse_snapshot,
    )
    result["label"] = args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "run.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    log_result(result)
    log(f"saved {out_dir.relative_to(REPO_ROOT)}/run.json and pricing_snapshot.*")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
