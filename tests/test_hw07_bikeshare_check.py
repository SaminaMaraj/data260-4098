"""Offline tests for the Part 4 deterministic validator and the bounded validation
round. Run: python tests/test_hw07_bikeshare_check.py (scripted model, no Ollama)."""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.hw7_bikeshare_check import (  # noqa: E402
    feedback_message,
    reference_costs,
    reference_prices,
    validate,
)
from src.hw7_bikeshare_tools import load_trips  # noqa: E402

RAW = REPO_ROOT / "reports" / "hw07" / "raw"
SNAPSHOT = RAW / "bikeshare" / "history" / "scenario_A_unlock_omitted"
SNAPSHOT_TXT = SNAPSHOT / "pricing_snapshot.txt"
SCENARIO_A = RAW / "scenarios" / "scenario_A_membership.csv"
SCENARIO_B = RAW / "scenarios" / "scenario_B_payg.csv"


def approx(a, b, tol=0.006):
    return a is not None and abs(a - b) <= tol


PRICES = {
    "MEMBERSHIP": 29.0,
    "UNLOCK": 1.0,
    "PAYG_CLASSIC": 0.19,
    "PAYG_EBIKE": 0.49,
    "INCLUDED": 45.0,
    "MEMBER_OVERAGE": 0.17,
    "MEMBER_EBIKE": 0.17,
}


def test_reference_prices_from_saved_snapshot():
    ref = reference_prices(SNAPSHOT_TXT.read_text(encoding="utf-8"))
    assert ref["ok"], ref
    assert ref["prices"] == PRICES
    assert ref["quotes"]["month_classic"] == "45 min free, then $0.17/min"


def test_reference_costs_both_scenarios():
    conn, _ = load_trips(SCENARIO_A.read_bytes())
    a = reference_costs(conn, PRICES)
    assert (a["rides"], a["rider_months"]) == (600, 15)
    assert approx(a["pay_per_use_total"], 4860.05)
    assert a["unlock_fees"] == 600
    assert a["membership_fees"] == 435
    assert approx(a["member_residual"], 1336.88)
    assert approx(a["membership_total"], 1771.88)
    assert approx(a["break_even_rides_per_rider_month"], 4.94)
    assert a["decision"] == "Buy Monthly Membership"
    assert approx(sum(w["payg_spend"] for w in a["weekly"]), 4860.05, 0.05)

    conn, _ = load_trips(SCENARIO_B.read_bytes())
    b = reference_costs(conn, PRICES)
    assert (b["rides"], b["rider_months"]) == (520, 260)
    assert approx(b["pay_per_use_total"], 1196.97)
    assert approx(b["membership_total"], 7540.0)
    assert approx(b["break_even_rides_per_rider_month"], 12.6)
    assert b["decision"] == "Pay Per Ride/Minute"


def test_validate_flags_missing_unlock_and_mixed_labels():
    """The historical scenario A answer must fail with a precise hint."""
    conn, _ = load_trips(SCENARIO_A.read_bytes())
    ref_prices = {"ok": True, "prices": PRICES}
    ref = reference_costs(conn, PRICES)
    old = json.loads((SNAPSHOT / "run.json").read_text(encoding="utf-8"))
    result = validate(
        old["final"], old["weekly"], ref_prices, ref, "Buy Monthly Membership"
    )
    failed = {c["check"]: c for c in result["checks"] if not c["ok"]}
    assert not result["passed"]
    assert "unlock fee is missing" in failed["pay_per_use_total"]["hint"]
    assert "membership_fees (passes only)" in failed  # 1771.88 was the total
    assert "break_even_rides_per_rider_month" in failed  # 5.95 vs 4.94
    assert "weekly table (rides and spend per week)" in failed


def test_decision_only_failure_gets_decision_feedback():
    """Right numbers, wrong decision (seen in a real qwen3:8b run): the feedback
    must point at the decision, not ask to recompute correct numbers."""
    conn, _ = load_trips(SCENARIO_A.read_bytes())
    ref = reference_costs(conn, PRICES)
    final = {
        k: ref[k]
        for k in (
            "pay_per_use_total",
            "membership_fees",
            "member_residual",
            "membership_total",
            "break_even_rides_per_rider_month",
            "actual_rides_per_rider_month",
        )
    }
    final["prices_used"] = PRICES
    result = validate(
        final, ref["weekly"], {"ok": True, "prices": PRICES}, ref, "Pay Per Ride/Minute"
    )
    failed = {c["check"] for c in result["checks"] if not c["ok"]}
    assert failed == {
        "consistency: decision follows own totals",
        "decision matches recomputed costs",
    }
    text = feedback_message(result)
    assert "do not recompute" in text and "LOWER total" in text
    assert "Recompute the failed values" not in text


def test_every_failed_check_gets_a_formula_hint_not_the_answer():
    """Seen in a real run: break-even reported as 2.0 (the actual rides)."""
    conn, _ = load_trips(SCENARIO_B.read_bytes())
    ref = reference_costs(conn, PRICES)
    final = {
        k: ref[k]
        for k in (
            "pay_per_use_total",
            "membership_fees",
            "member_residual",
            "membership_total",
            "actual_rides_per_rider_month",
        )
    }
    final |= {"prices_used": PRICES, "break_even_rides_per_rider_month": 2.0}
    result = validate(
        final, ref["weekly"], {"ok": True, "prices": PRICES}, ref, "Pay Per Ride/Minute"
    )
    failed = [c for c in result["checks"] if not c["ok"]]
    assert [c["check"] for c in failed] == ["break_even_rides_per_rider_month"]
    text = feedback_message(result)
    assert "MEMBERSHIP / ((pay_per_use_total - member_residual) / rides)" in text
    assert "12.6" not in text  # the reference value is never given away


# --------------------------------------------------------------------------- #
# bounded validation round with a scripted model
# --------------------------------------------------------------------------- #
def _scripted_model(fix_on_feedback: bool):
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from langchain_core.outputs import ChatGeneration, ChatResult

    def sql(unlock: str) -> tuple[str, str]:
        payg = "CASE WHEN is_ebike=1 THEN 0.49*duration_min ELSE 0.19*duration_min END"
        summary = (
            "SELECT COUNT(*) AS rides, COUNT(DISTINCT rider_id || ride_month) AS "
            f"rider_months, ROUND(SUM({payg}),2) AS payg_minute_cost, ROUND(SUM(CASE "
            "WHEN is_ebike=1 THEN 0.17*duration_min WHEN duration_min > 45 THEN "
            "0.17*(duration_min - 45) ELSE 0 END),2) AS member_residual FROM trips"
        )
        weekly = (
            "SELECT week_start, COUNT(*) AS rides, ROUND(AVG(duration_min),1) AS "
            f"avg_min, ROUND({unlock}SUM({payg}),2) AS payg_spend FROM trips GROUP "
            "BY week_start ORDER BY week_start"
        )
        return summary, weekly

    class Scripted(BaseChatModel):
        @property
        def _llm_type(self):
            return "scripted"

        def bind_tools(self, tools, **kw):
            return self

        def _generate(self, messages, stop=None, run_manager=None, **kw):
            url = re.search(r"Pricing page URL: (\S+)", messages[1].content).group(1)
            feedback = any(
                isinstance(m, HumanMessage) and "Validation check failed" in m.content
                for m in messages
            )
            fixed = feedback and fix_on_feedback
            summary, weekly = sql("COUNT(*)*1 + " if fixed else "")
            phase = [m for m in messages if isinstance(m, ToolMessage)]
            if feedback:  # only count tool calls made after the feedback
                cut = max(
                    i
                    for i, m in enumerate(messages)
                    if isinstance(m, HumanMessage) and "Validation" in m.content
                )
                phase = [m for m in messages[cut:] if isinstance(m, ToolMessage)]
            plan = [("csv_sql", {"sql": summary}), ("csv_sql", {"sql": weekly})]
            if not feedback:
                plan.insert(0, ("policy_retriever", {"url": url, "query": "price"}))
            if len(phase) < len(plan):
                name, args = plan[len(phase)]
                call = {"name": name, "args": args, "id": f"c{len(messages)}"}
                msg = AIMessage(content="", tool_calls=[call])
                return ChatResult(generations=[ChatGeneration(message=msg)])
            rows = json.loads(phase[-2].content)["data"]["rows"][0]
            unlock = rows["rides"] * 1.0 if fixed else 0.0
            pay = round(unlock + rows["payg_minute_cost"], 2)
            fees = rows["rider_months"] * 29.0
            total = round(fees + rows["member_residual"], 2)
            answer = {
                "decision": "Buy Monthly Membership"
                if total < pay
                else "Pay Per Ride/Minute",
                "prices_used": PRICES,
                "pay_per_use_total": pay,
                "membership_fees": fees if fixed else total,
                "member_residual": rows["member_residual"],
                "membership_total": total,
                "break_even_rides_per_rider_month": round(
                    29 / ((pay - rows["member_residual"]) / rows["rides"]), 2
                ),
                "actual_rides_per_rider_month": rows["rides"] / rows["rider_months"],
            }
            msg = AIMessage(content=json.dumps(answer))
            return ChatResult(generations=[ChatGeneration(message=msg)])

    return Scripted()


def _bounded_validation_round(fix: bool) -> None:
    from src.hw7_bikeshare_agent import run_bikeshare_agent

    tmp_path = Path(tempfile.mkdtemp(prefix="hw7_bikeshare_"))

    result = run_bikeshare_agent(
        SCENARIO_A.read_bytes(),
        "https://www.lyft.com/bikes/bay-wheels/pricing",
        snapshot_dir=tmp_path,
        reuse_snapshot=SNAPSHOT / "pricing_snapshot.json",
        llm=_scripted_model(fix_on_feedback=fix),
    )
    rounds = result["validation"]["rounds"]
    assert len(rounds) == 2  # first answer + exactly one correction round
    assert not rounds[0]["passed"]
    assert approx(result["first_answer"]["pay_per_use_total"], 4260.05)
    assert result["citations"][0]["snapshot_mode"] == "reused_saved_snapshot"
    steps = [s["tool"] for s in result["timeline"]]
    assert steps.count("validation_check") == 2 and "validation_feedback" in steps
    if fix:
        assert (
            result["validated"] and result["metrics"]["stop_reason"] == "final_answer"
        )
        assert approx(result["final"]["pay_per_use_total"], 4860.05)
        assert approx(result["final"]["membership_fees"], 435.0)
    else:
        assert not result["validated"]
        assert result["metrics"]["stop_reason"] == "validation_failed"


def test_validation_round_corrects_answer():
    _bounded_validation_round(fix=True)


def test_validation_round_rejects_uncorrected_answer():
    _bounded_validation_round(fix=False)


def main() -> int:
    print("Kazi Samina Maraj Mumu")
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
            print(f"PASS {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
