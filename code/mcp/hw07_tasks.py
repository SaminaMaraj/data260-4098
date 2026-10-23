"""HW7 fixed verification tasks (A, B, C, error recovery) and their verifiers.

Each verifier is deterministic: it recomputes the expected answer by calling
the same domain tools directly through execute_tool() (no model involved) and
then checks the agent's trace and final answer against it.
"""

from __future__ import annotations

import json
import re
from typing import Any

from execute_tool import execute_tool

CODE_RE = re.compile(r"INC-\d{6}")
ROUTE_CODE_RE = re.compile(r"RT-\d{3}")

TASKS: dict[str, dict[str, Any]] = {
    "A": {
        "name": "search then detail lookup",
        "prompt": (
            "Search for delay incidents on VTA Route 22: call search_incidents with "
            "query 'VTA Route 22', category 'delay' and limit 5. Then call "
            "get_incident on the FIRST search result and report its incident code, "
            "title, route and submission date."
        ),
        "required_tools": ["search_incidents", "get_incident"],
    },
    "B": {
        "name": "aggregate then supporting example",
        "prompt": (
            "Which route has the most incidents? First call incident_count_by_route. "
            "Then call search_incidents with that route's name as the query and "
            "limit 1, and give the route name, its incident count and one "
            "supporting incident code from that route."
        ),
        "required_tools": ["incident_count_by_route", "search_incidents"],
    },
    "C": {
        "name": "compare two entities (search + two lookups)",
        "prompt": (
            "Compare the first two collision incidents: call search_incidents with "
            "query 'collision', category 'collision' and limit 2, then call "
            "get_incident on each of the two incident codes, and compare their "
            "routes and submission dates."
        ),
        "required_tools": ["search_incidents", "get_incident", "get_incident"],
    },
}

ERROR_TASK = {
    "name": "error recovery: nonexistent incident",
    "prompt": "Get the full details of incident INC-999999 and summarize it.",
    "missing_code": "INC-999999",
}


def _tool(name: str, args: dict) -> dict:
    return json.loads(execute_tool(name, args))


def ground_truth(task_id: str) -> dict[str, Any]:
    """Expected facts, computed from the tools without any model."""
    if task_id == "A":
        result = _tool(
            "search_incidents",
            {"query": "VTA Route 22", "category": "delay", "limit": 5},
        )
        first = result["data"][0]
        return {"code": first["incident_code"], "title": first["incident_title"]}
    if task_id == "B":
        counts = _tool("incident_count_by_route", {"min_incidents": 0})["data"]
        top = max(row["incident_count"] for row in counts)
        leaders = [row for row in counts if row["incident_count"] == top]
        return {
            "route_names": [row["route_name"] for row in leaders],
            "route_codes": [row["route_code"] for row in leaders],
            "route_ids": [row["route_id"] for row in leaders],
            "count": top,
        }
    if task_id == "C":
        result = _tool(
            "search_incidents",
            {"query": "collision", "category": "collision", "limit": 2},
        )
        return {"codes": [row["incident_code"] for row in result["data"]]}
    raise KeyError(task_id)


def _observed_text(trace: list[dict]) -> str:
    return json.dumps([step.get("result") for step in trace if "result" in step])


def unsupported_claims(answer: str, trace: list[dict]) -> list[str]:
    """Incident/route codes in the answer that no tool observation contained."""
    observed = _observed_text(trace)
    claimed = set(CODE_RE.findall(answer or "")) | set(
        ROUTE_CODE_RE.findall(answer or "")
    )
    return sorted(code for code in claimed if code not in observed)


def _called(trace: list[dict], tool: str, **match: Any) -> bool:
    for step in trace:
        if step.get("tool") != tool or "result" not in step:
            continue
        if all(step["input"].get(k) == v for k, v in match.items()):
            return True
    return False


def _chain_complete(task_id: str, trace: list[dict]) -> bool:
    executed = [s["tool"] for s in trace if "result" in s]
    needed = list(TASKS[task_id]["required_tools"])
    position = 0
    for tool in executed:  # required tools must appear in order
        if position < len(needed) and tool == needed[position]:
            position += 1
    return position == len(needed)


def _digits_present(answer: str, code: str) -> bool:
    digits = code.split("-")[1]
    return bool(re.search(rf"\b(INC[-\s]?)?0*{int(digits)}\b", answer or ""))


def verify(task_id: str, run: dict[str, Any], truth: dict | None = None) -> dict:
    """Strict deterministic check + a relaxed check used to flag false rejections."""
    truth = truth or ground_truth(task_id)
    answer = run.get("answer") or ""
    trace = run.get("trace") or []
    chain = _chain_complete(task_id, trace)
    checks: dict[str, bool] = {"tool_chain_complete": chain}

    if task_id == "A":
        code = truth["code"]
        checks["looked_up_first_result"] = _called(
            trace, "get_incident", incident_code=code
        )
        checks["answer_has_code"] = code in answer
        relaxed = _digits_present(answer, code) or truth["title"] in answer
    elif task_id == "B":
        names = truth["route_names"]
        checks["answer_names_top_route"] = any(
            n in answer for n in names + truth["route_codes"]
        )
        example_ok = False
        for code in CODE_RE.findall(answer):
            detail = _tool("get_incident", {"incident_code": code})
            if detail["ok"] and detail["data"]["route_id"] in truth["route_ids"]:
                example_ok = True
                break
        checks["supporting_example_on_top_route"] = example_ok
        short_names = [n.replace("VTA ", "") for n in names]
        relaxed = any(n.casefold() in answer.casefold() for n in short_names)
    elif task_id == "C":
        codes = truth["codes"]
        checks["looked_up_both"] = all(
            _called(trace, "get_incident", incident_code=c) for c in codes
        )
        checks["answer_has_both_codes"] = all(c in answer for c in codes)
        relaxed = all(_digits_present(answer, c) for c in codes)
    else:
        raise KeyError(task_id)

    passed = all(checks.values())
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "task": task_id,
        "passed": passed,
        "checks": checks,
        "failed_assertions": failed,
        "expected": truth,
        "unsupported_claims": unsupported_claims(answer, trace),
        # strict rejected, but the answer's facts are right in another format:
        "false_rejection_candidate": (not passed) and bool(relaxed) and chain,
    }


def verify_error_recovery(run: dict[str, Any]) -> dict:
    code = ERROR_TASK["missing_code"]
    tool_saw_error = any(
        step.get("tool") == "get_incident"
        and "result" in step
        and step["result"]["ok"] is False
        for step in run.get("trace", [])
    )
    answer = run.get("answer") or ""
    invented = [c for c in CODE_RE.findall(answer) if c != code]
    checks = {
        "execute_tool_returned_error_envelope": tool_saw_error,
        "agent_finished_cleanly": run.get("stop_reason") == "final_answer",
        "no_invented_incident": not invented,
    }
    return {"passed": all(checks.values()), "checks": checks}
