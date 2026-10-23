"""HW7 Part 2 - hand-written agent loop over the three HW5 transit tools.

run_agent(user_input) uses the HW1 model adapter (src/model_client.complete),
executes every tool call through the HW5 single entry point execute_tool(),
appends each result as a role="tool" message, and loops until the model gives
a final answer or a hard iteration ceiling is reached.

Repair path: an unknown tool name, malformed JSON arguments, or a schema
violation is NOT executed. The model is re-prompted once with the specific
problem; after MAX_REPAIRS failed repairs the run stops cleanly with
stop_reason="repair_exhausted".
"""

from __future__ import annotations

import json
import re
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

MCP_DIR = Path(__file__).resolve().parent
CODE_DIR = MCP_DIR.parent
REPO_ROOT = CODE_DIR.parent
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != CODE_DIR.resolve()]
if str(MCP_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from execute_tool import _validated_inputs, execute_tool

MAX_ITERATIONS = 8
MAX_REPAIRS = 2
INCIDENT_CODE = re.compile(r"^INC-\d{6}$")
CATEGORIES = ["delay", "collision", "service-suspension", "infrastructure-issue"]

SYSTEM_PROMPT = (
    "You are a municipal transit incident assistant (VTA routes). Use the tools "
    "to answer; never invent incident codes, routes, dates or counts. Call one "
    "tool at a time and wait for its result before the next call. Tool results "
    "are JSON envelopes {ok, data, error}; if ok is false, read the error and "
    "explain it instead of guessing. When the task is complete, answer in at "
    "most 5 sentences and quote the exact incident codes (INC-######) you used."
)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_incidents",
            "description": (
                "Search incidents by text in code, title, route line or "
                "description. Results are ordered by incident id (oldest first)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search text, e.g. 'delay' or 'VTA Route 22'",
                    },
                    "category": {"type": "string", "enum": CATEGORIES},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_incident",
            "description": "Get full details of one incident by its code.",
            "parameters": {
                "type": "object",
                "properties": {
                    "incident_code": {
                        "type": "string",
                        "pattern": "^INC-\\d{6}$",
                        "description": "Incident code such as INC-000002",
                    }
                },
                "required": ["incident_code"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "incident_count_by_route",
            "description": "Count incidents grouped by route (aggregate).",
            "parameters": {
                "type": "object",
                "properties": {"min_incidents": {"type": "integer", "minimum": 0}},
                "additionalProperties": False,
            },
        },
    },
]
TOOL_NAMES = {tool["function"]["name"] for tool in TOOL_SCHEMAS}

# Failure classes required by the reliability measurement.
MALFORMED = "malformed_arguments"
UNKNOWN_TOOL = "unknown_tool"
TEXT_INSTEAD = "text_when_tool_required"
LOST_CHAIN = "lost_multi_step_chain"


def default_model(messages, tools, temperature=None):
    """The HW1 adapter (Ollama qwen3:8b), imported lazily so tests stay offline."""
    from src.model_client import complete

    return complete(messages, tools, temperature=temperature)


def validate_call(
    name: Any, raw_args: Any
) -> tuple[dict | None, str | None, str | None]:
    """Return (args, problem, failure_type). problem=None means well-formed."""
    if not isinstance(name, str) or name not in TOOL_NAMES:
        return (
            None,
            f"unknown tool '{name}'. Valid tools: {', '.join(sorted(TOOL_NAMES))}.",
            UNKNOWN_TOOL,
        )
    args = raw_args
    if args is None:
        args = {}
    if isinstance(args, str):
        try:
            args = json.loads(args) if args.strip() else {}
        except json.JSONDecodeError as exc:
            return None, f"arguments are not valid JSON ({exc.msg}).", MALFORMED
    if not isinstance(args, dict):
        return None, "arguments must be a JSON object.", MALFORMED

    validated, error = _validated_inputs(name, args)
    if error:
        return None, f"schema validation failed for {name}: {error}.", MALFORMED
    if name == "search_incidents":
        if (
            validated["category"] is not None
            and validated["category"] not in CATEGORIES
        ):
            return None, f"category must be one of {CATEGORIES}.", MALFORMED
        if validated["limit"] > 50:
            return None, "limit must be between 1 and 50.", MALFORMED
    if name == "get_incident" and not INCIDENT_CODE.fullmatch(
        validated["incident_code"].strip()
    ):
        return None, "incident_code must match INC-###### (6 digits).", MALFORMED
    return args, None, None


_TEXT_CALL = re.compile(r"\{.*\}", re.DOTALL)


def _extract_calls(response: dict[str, Any]) -> list[tuple[Any, Any]]:
    """Native tool calls, or a JSON tool call that the model printed as text."""
    calls = []
    for call in response.get("tool_calls") or []:
        function = call.get("function", call)
        calls.append((function.get("name"), function.get("arguments")))
    if calls:
        return calls
    content = response.get("content") or ""
    match = _TEXT_CALL.search(content)
    if match and ('"name"' in match.group(0) or '"tool"' in match.group(0)):
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return [("<unparseable text tool call>", match.group(0))]
        if isinstance(parsed, dict):
            name = parsed.get("name") or parsed.get("tool")
            return [(name, parsed.get("arguments", parsed.get("input", {})))]
    return []


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()


def run_agent(
    user_input: str,
    *,
    model: Callable[..., dict] | None = None,
    temperature: float | None = None,
    max_iterations: int = MAX_ITERATIONS,
    max_repairs: int = MAX_REPAIRS,
    require_tool: bool = True,
    extra_messages: list[dict[str, str]] | None = None,
    tool_budget: int | None = None,
    token_budget: int | None = None,
    log: Callable[[str], None] | None = print,
) -> dict[str, Any]:
    """Run one task. Returns answer, stop_reason, trace and counters."""
    chat = model or default_model
    say = log or (lambda _line: None)
    run_id = uuid.uuid4().hex[:8]
    started = time.perf_counter()
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += extra_messages or []
    messages.append({"role": "user", "content": user_input})

    trace: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    proposed = well_formed_first = repairs_used = repaired_ok = executed = 0
    pending_repair = False
    tokens = 0
    answer = ""
    iteration = 0

    def finish(reason: str) -> dict[str, Any]:
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        say(
            f"[{run_id}] stop_reason={reason} iterations={iteration} "
            f"total_tool_calls={executed} repairs={repairs_used} tokens={tokens} "
            f"latency_ms={latency_ms}"
        )
        return {
            "run_id": run_id,
            "answer": answer,
            "stop_reason": reason,
            "iterations": iteration,
            "tool_calls": executed,
            "proposed_calls": proposed,
            "well_formed_first_try": well_formed_first,
            "repairs_used": repairs_used,
            "repaired_ok": repaired_ok,
            "failures": failures,
            "tokens": tokens,
            "latency_ms": latency_ms,
            "trace": trace,
        }

    for iteration in range(1, max_iterations + 1):
        if token_budget is not None and tokens >= token_budget:
            return finish("budget_exhausted")
        response = chat(messages, TOOL_SCHEMAS, temperature=temperature)
        tokens += int(response.get("total_tokens", 0))
        content = _strip_thinking(response.get("content", ""))
        calls = _extract_calls(response)

        if not calls:
            if require_tool and executed == 0:
                failures.append({"type": TEXT_INSTEAD, "detail": content[:160]})
                say(f"[{run_id}] iter {iteration}: text instead of a tool call")
                if repairs_used >= max_repairs:
                    answer = content
                    return finish("repair_exhausted")
                repairs_used += 1
                pending_repair = True
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Problem: you answered in text, but this task requires "
                            "calling a tool first. Call one of: "
                            + ", ".join(sorted(TOOL_NAMES))
                            + "."
                        ),
                    }
                )
                continue
            answer = content
            return finish("final_answer")

        native = [
            {"function": {"name": n, "arguments": a if isinstance(a, dict) else {}}}
            for n, a in calls
        ]
        messages.append({"role": "assistant", "content": content, "tool_calls": native})

        for name, raw_args in calls:
            proposed += 1
            args, problem, failure_type = validate_call(name, raw_args)
            if problem:
                failures.append({"type": failure_type, "detail": problem})
                say(
                    f"[{run_id}] iter {iteration}: REJECTED {name} {raw_args!r}: "
                    f"{problem}"
                )
                trace.append(
                    {
                        "iteration": iteration,
                        "tool": name,
                        "input": raw_args,
                        "rejected": problem,
                        "failure_type": failure_type,
                    }
                )
                if repairs_used >= max_repairs:
                    return finish("repair_exhausted")
                repairs_used += 1
                pending_repair = True
                messages.append(
                    {
                        "role": "tool",
                        "tool_name": str(name),
                        "content": json.dumps(
                            {
                                "ok": False,
                                "data": None,
                                "error": f"Problem: {problem} Fix the call and retry.",
                            }
                        ),
                    }
                )
                continue

            if pending_repair:
                repaired_ok += 1  # a well-formed call that fixes a rejected one
                pending_repair = False
            else:
                well_formed_first += 1
            if tool_budget is not None and executed >= tool_budget:
                return finish("budget_exhausted")

            result_text = execute_tool(name, args)
            executed += 1
            result = json.loads(result_text)
            data = result["data"]
            size = len(data) if isinstance(data, list) else 1
            outcome = (
                f"error={result['error']}" if not result["ok"] else f"items={size}"
            )
            say(
                f"[{run_id}] iter {iteration}: TOOL {name} "
                f"input={json.dumps(args)} ok={result['ok']} {outcome}"
            )
            trace.append(
                {"iteration": iteration, "tool": name, "input": args, "result": result}
            )
            messages.append({"role": "tool", "tool_name": name, "content": result_text})

    return finish("max_iterations")
