"""HW7 Part 4 - deterministic validator for the Bay Wheels agent's final answer.

The agent (LangGraph ReAct + three MRKL tools) still does the work. This module
only CHECKS its structured result:

1. reference_prices() reads the saved pricing-page snapshot text and extracts
   the Month pass and Single ride prices with fixed rules (no model).
2. reference_costs() recomputes every number of the cost breakdown from the
   loaded trips with those prices (plain SQL, no model).
3. validate() compares the agent's numbers with the reference numbers and
   returns one pass/fail entry per check.

Pricing rules (from the Bay Wheels page, column "Month pass" vs "Single ride"):
- pay-per-use ride  = UNLOCK + PAYG_CLASSIC or PAYG_EBIKE * minutes
- member classic    = first INCLUDED minutes free, then MEMBER_OVERAGE per minute
- member ebike      = free unlock + MEMBER_EBIKE per minute (no free minutes)
- membership fees   = one pass per (rider, month) pair * MEMBERSHIP
Minutes are whole minutes rounded up (duration_min in the trips table).
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

PRICE_KEYS = (
    "MEMBERSHIP",
    "UNLOCK",
    "PAYG_CLASSIC",
    "PAYG_EBIKE",
    "INCLUDED",
    "MEMBER_OVERAGE",
    "MEMBER_EBIKE",
)
_MONEY = r"\$(\d+(?:\.\d+)?)"


def _plan_columns(lines: list[str]) -> list[str] | None:
    """The comparison table lists the plan names once, in column order."""
    for i, line in enumerate(lines):
        if line == "Single ride" and i + 2 < len(lines) and lines[i + 1] == "Day pass":
            names = []
            for name in lines[i : i + 6]:
                if name.startswith("$"):
                    break
                names.append(name)
            return names
    return None


def reference_prices(snapshot_text: str) -> dict[str, Any]:
    """Extract Single-ride and Month-pass prices from the saved page text."""
    lines = [line.strip() for line in snapshot_text.splitlines() if line.strip()]
    columns = _plan_columns(lines)
    if not columns or "Month pass" not in columns:
        return {"ok": False, "reason": "plan columns not found in snapshot"}
    single, month = columns.index("Single ride"), columns.index("Month pass")
    try:
        classic_at = lines.index("Classic bike prices")
        ebike_at = lines.index("Ebike prices", classic_at)
    except ValueError:
        return {"ok": False, "reason": "price rows not found in snapshot"}
    classic = lines[classic_at + 1 : classic_at + 1 + len(columns) - 1]
    ebike = lines[ebike_at + 1 : ebike_at + 1 + len(columns) - 1]
    # "Lyft Pink" and "All Access" are one column, so price rows have 5 cells.
    try:
        single_classic = re.fullmatch(
            _MONEY + r" to unlock, then " + _MONEY + r"/min", classic[single]
        )
        single_ebike = re.fullmatch(
            _MONEY + r" unlock \+ " + _MONEY + r"/min", ebike[single]
        )
        month_classic = re.fullmatch(
            r"(\d+) min free, then " + _MONEY + r"/min", classic[month]
        )
        month_ebike = re.fullmatch(r"Free unlocks \+ " + _MONEY + r"/min", ebike[month])
        month_price = re.search(_MONEY + r"/month", " ".join(lines))
    except IndexError:
        return {"ok": False, "reason": "price rows shorter than plan columns"}
    if not all([single_classic, single_ebike, month_classic, month_ebike, month_price]):
        return {"ok": False, "reason": "price text did not match the expected format"}
    if single_classic.group(1) != single_ebike.group(1):
        return {"ok": False, "reason": "classic and ebike unlock fees differ"}
    prices = {
        "MEMBERSHIP": float(month_price.group(1)),
        "UNLOCK": float(single_classic.group(1)),
        "PAYG_CLASSIC": float(single_classic.group(2)),
        "PAYG_EBIKE": float(single_ebike.group(2)),
        "INCLUDED": float(month_classic.group(1)),
        "MEMBER_OVERAGE": float(month_classic.group(2)),
        "MEMBER_EBIKE": float(month_ebike.group(1)),
    }
    quotes = {
        "single_classic": classic[single],
        "single_ebike": ebike[single],
        "month_classic": classic[month],
        "month_ebike": ebike[month],
        "month_price": month_price.group(0),
    }
    return {"ok": True, "prices": prices, "quotes": quotes}


def reference_costs(conn: sqlite3.Connection, p: dict[str, float]) -> dict[str, Any]:
    """Recompute the whole cost breakdown from the trips table (no model)."""
    payg_ride = "(? + CASE WHEN is_ebike=1 THEN ? ELSE ? END * duration_min)"
    member_ride = (
        "(CASE WHEN is_ebike=1 THEN ? * duration_min "
        "WHEN duration_min > ? THEN ? * (duration_min - ?) ELSE 0 END)"
    )
    payg_args = (p["UNLOCK"], p["PAYG_EBIKE"], p["PAYG_CLASSIC"])
    member_args = (p["MEMBER_EBIKE"], p["INCLUDED"], p["MEMBER_OVERAGE"], p["INCLUDED"])
    row = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT rider_id), "
        "COUNT(DISTINCT rider_id || '|' || ride_month), AVG(duration_min), "
        f"SUM(is_ebike), SUM({payg_ride}), SUM({member_ride}) FROM trips",
        payg_args + member_args,
    ).fetchone()
    rides, riders, rider_months, avg_min, ebike_rides, payg, residual = row
    weekly = [
        {"week_start": w, "rides": n, "avg_min": round(a, 1), "payg_spend": round(s, 2)}
        for w, n, a, s in conn.execute(
            "SELECT week_start, COUNT(*), AVG(duration_min), "
            f"SUM({payg_ride}) FROM trips GROUP BY week_start ORDER BY week_start",
            payg_args,
        )
    ]
    fees = rider_months * p["MEMBERSHIP"]
    member_total = fees + residual
    saving_per_ride = (payg - residual) / rides if rides else 0.0
    break_even = p["MEMBERSHIP"] / saving_per_ride if saving_per_ride > 0 else None
    return {
        "rides": rides,
        "riders": riders,
        "rider_months": rider_months,
        "ebike_rides": ebike_rides,
        "avg_min": round(avg_min, 2),
        "unlock_fees": round(rides * p["UNLOCK"], 2),
        "pay_per_use_total": round(payg, 2),
        "membership_fees": round(fees, 2),
        "member_residual": round(residual, 2),
        "membership_total": round(member_total, 2),
        "saving_per_ride": round(saving_per_ride, 4),
        "break_even_rides_per_rider_month": None
        if break_even is None
        else round(break_even, 2),
        "actual_rides_per_rider_month": round(rides / rider_months, 2),
        "decision": "Buy Monthly Membership"
        if member_total < payg
        else "Pay Per Ride/Minute",
        "weekly": weekly,
    }


def _num(value: Any) -> float | None:
    try:
        return float(str(value).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _close(agent: float | None, expected: float | None, rel: float, floor: float):
    if agent is None or expected is None:
        return False
    return abs(agent - expected) <= max(floor, rel * abs(expected))


def validate(
    final: dict[str, Any],
    weekly: list[dict[str, Any]],
    ref_prices: dict[str, Any],
    ref: dict[str, Any] | None,
    decision: str | None,
) -> dict[str, Any]:
    """Compare the agent's structured answer with the deterministic reference."""
    checks: list[dict[str, Any]] = []

    def add(name, agent, expected, ok, hint=""):
        checks.append(
            {"check": name, "agent": agent, "expected": expected, "ok": bool(ok)}
            | ({"hint": hint} if hint and not ok else {})
        )

    if not ref_prices.get("ok") or ref is None:
        return {
            "passed": False,
            "checks": [],
            "reason": f"reference unavailable: {ref_prices.get('reason')}",
        }
    used = final.get("prices_used") or {}
    for key in PRICE_KEYS:
        agent = _num(used.get(key))
        add(
            f"price {key}",
            agent,
            ref_prices["prices"][key],
            agent is not None and abs(agent - ref_prices["prices"][key]) < 1e-6,
        )

    pay = _num(final.get("pay_per_use_total"))
    fees = _num(final.get("membership_fees"))
    residual = _num(final.get("member_residual"))
    total = _num(final.get("membership_total"))
    gap = None if pay is None else round(ref["pay_per_use_total"] - pay, 2)
    add(
        "pay_per_use_total",
        pay,
        ref["pay_per_use_total"],
        _close(pay, ref["pay_per_use_total"], 0.002, 0.5),
        "difference equals rides x UNLOCK: the unlock fee is missing"
        if gap is not None and abs(gap - ref["unlock_fees"]) < 0.5
        else "",
    )
    add(
        "membership_fees (passes only)",
        fees,
        ref["membership_fees"],
        _close(fees, ref["membership_fees"], 0.002, 0.5),
        "membership_fees must be rider_months x MEMBERSHIP, without residual charges",
    )
    add(
        "member_residual",
        residual,
        ref["member_residual"],
        _close(residual, ref["member_residual"], 0.002, 0.5),
    )
    add(
        "membership_total = fees + residual",
        total,
        ref["membership_total"],
        _close(total, ref["membership_total"], 0.002, 0.5)
        and fees is not None
        and residual is not None
        and _close(total, fees + residual, 0.0, 0.05),
    )
    for key in ("break_even_rides_per_rider_month", "actual_rides_per_rider_month"):
        agent = _num(final.get(key))
        add(key, agent, ref[key], _close(agent, ref[key], 0.01, 0.05))

    # consistency check: the decision must follow from the agent's own totals
    implied = None
    if pay is not None and total is not None:
        implied = "Buy Monthly Membership" if total < pay else "Pay Per Ride/Minute"
    add(
        "consistency: decision follows own totals",
        decision,
        implied,
        decision == implied,
    )
    add(
        "decision matches recomputed costs",
        decision,
        ref["decision"],
        decision == ref["decision"],
    )

    by_week = {w["week_start"]: w for w in weekly or []}
    week_ok = bool(weekly) and len(by_week) == len(ref["weekly"])
    for expected in ref["weekly"]:
        got = by_week.get(expected["week_start"]) or {}
        week_ok = (
            week_ok
            and _num(got.get("rides")) == expected["rides"]
            and _close(_num(got.get("payg_spend")), expected["payg_spend"], 0.002, 0.05)
        )
    add(
        "weekly table (rides and spend per week)",
        len(weekly or []),
        len(ref["weekly"]),
        week_ok,
        "weekly payg_spend must include COUNT(*) * UNLOCK",
    )
    return {"passed": all(c["ok"] for c in checks), "checks": checks}


def feedback_message(result: dict[str, Any]) -> str:
    """Short, concrete correction request for the agent (logged in the timeline)."""
    lines = [
        "Validation check failed. A deterministic recomputation from the trips "
        "table and the saved pricing page does not match these fields:"
    ]
    for c in result["checks"]:
        if not c["ok"]:
            line = f"- {c['check']}: you reported {c['agent']}"
            if c.get("hint"):
                line += f" ({c['hint']})"
            lines.append(line)
    lines.append(
        "Recompute the failed values with csv_sql and calculator, following the "
        "steps in the instructions, then reply with the corrected JSON object only."
    )
    return "\n".join(lines)
