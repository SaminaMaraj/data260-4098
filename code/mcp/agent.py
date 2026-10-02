"""Small Ollama tool-using agent for the HW5 transit tools."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx


MCP_DIR = Path(__file__).resolve().parent
REPO_ROOT = MCP_DIR.parents[1]
# Running a script from code/ puts code/ first on sys.path; remove it so the
# real installed mcp package is never shadowed by code/mcp/.
sys.path[:] = [
    item
    for item in sys.path
    if Path(item or ".").resolve() != Path(__file__).resolve().parent.parent
]
sys.path.insert(0, str(MCP_DIR))

from execute_tool import execute_tool


DEFAULT_MODEL = "qwen3:8b"
DEFAULT_BASE_URL = "http://localhost:11434"
LOG_PATH = REPO_ROOT / "reports" / "hw05" / "raw" / "agent_runs.jsonl"

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "search_incidents",
            "description": "Search municipal transit incidents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "category": {"type": ["string", "null"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_incident",
            "description": "Get one municipal transit incident by code.",
            "parameters": {
                "type": "object",
                "properties": {"incident_code": {"type": "string"}},
                "required": ["incident_code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "incident_count_by_route",
            "description": "Count incidents grouped by route.",
            "parameters": {
                "type": "object",
                "properties": {
                    "min_incidents": {"type": "integer", "minimum": 0}
                },
            },
        },
    },
]


class OllamaModel:
    """Minimal native /api/chat client with JSON-selection fallback."""

    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_BASE_URL):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def chat(self, messages, tools):
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {"temperature": 0.0},
        }
        try:
            with httpx.Client(timeout=45.0) as client:
                response = client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                return response.json()
        except Exception:
            return self._json_selection(messages)

    def _json_selection(self, messages):
        fallback_messages = list(messages)
        fallback_messages.append(
            {
                "role": "system",
                "content": (
                    "Return only JSON. If a transit tool is needed, return "
                    '{"tool":"tool_name","input":{...}}. Otherwise return '
                    '{"final":"short answer"}. Available tools: '
                    "search_incidents, get_incident, incident_count_by_route."
                ),
            }
        )
        payload = {
            "model": self.model,
            "messages": fallback_messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }
        with httpx.Client(timeout=45.0) as client:
            response = client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()


class MockModel:
    """Offline scripted model used by tests and demonstrations."""

    def __init__(self, responses: list[dict[str, Any]] | None = None):
        self.responses = responses or [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "incident_count_by_route",
                                "arguments": {},
                            }
                        }
                    ],
                }
            }
        ]
        self.index = 0

    def chat(self, messages, tools):
        response = self.responses[min(self.index, len(self.responses) - 1)]
        self.index += 1
        return response


def _extract_tool_calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    message = response.get("message", {})
    native_calls = message.get("tool_calls") or response.get("tool_calls") or []
    if native_calls:
        return native_calls

    content = message.get("content", response.get("content", ""))
    if isinstance(content, dict):
        parsed = content
    else:
        try:
            parsed = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return []
    if not isinstance(parsed, dict) or "tool" not in parsed:
        return []
    return [
        {
            "function": {
                "name": parsed["tool"],
                "arguments": parsed.get("input", {}),
            }
        }
    ]


def _call_parts(tool_call: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    function = tool_call.get("function", tool_call)
    name = function.get("name")
    arguments = function.get("arguments", {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError:
            arguments = {}
    return name, arguments if isinstance(arguments, dict) else {}


def _write_log(entry: dict[str, Any], log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, separators=(",", ":")) + "\n")


def run_agent(user_input, model=None, max_steps=5, log_path=None):
    """Run the transit agent and return its final result and stop reason."""
    if max_steps < 1:
        raise ValueError("max_steps must be at least 1")
    selected_log_path = Path(log_path) if log_path is not None else LOG_PATH
    if model is None:
        selected_model = OllamaModel()
    elif hasattr(model, "chat"):
        selected_model = model
    else:
        selected_model = OllamaModel(model=str(model))
    run_id = str(uuid.uuid4())
    messages = [{"role": "user", "content": user_input}]
    tool_call_count = 0

    for step in range(1, max_steps + 1):
        response = selected_model.chat(messages, TOOL_DEFINITIONS)
        calls = _extract_tool_calls(response)
        if not calls:
            final = response.get("message", {}).get(
                "content", response.get("content", "")
            )
            _write_log(
                {
                    "run_id": run_id,
                    "step": step,
                    "tool": None,
                    "input": None,
                    "result": final,
                    "stop_reason": "completed",
                },
                selected_log_path,
            )
            return {
                "result": final,
                "stop_reason": "completed",
                "steps": step,
                "tool_calls": tool_call_count,
                "run_id": run_id,
            }

        # Ollama can return several calls in one response. Treat one model
        # turn as one agent step: execute only the first call and defer the
        # rest rather than counting parallel calls as separate steps.
        call = calls[0]
        tool, inputs = _call_parts(call)
        result_text = execute_tool(tool, inputs)
        result = json.loads(result_text)
        tool_call_count += 1
        safety_block = (
            not result.get("ok")
            and str(result.get("error", "")).startswith("safety policy:")
        )
        log_entry = {
            "run_id": run_id,
            "step": step,
            "tool": tool,
            "input": inputs,
            "result": result,
        }
        if len(calls) > 1:
            log_entry["ignored_tool_calls"] = [
                {
                    "tool": extra_tool,
                    "input": extra_inputs,
                }
                for extra_tool, extra_inputs in (
                    _call_parts(extra_call) for extra_call in calls[1:]
                )
            ]
        if safety_block:
            log_entry["stop_reason"] = "safety_block"
        elif step == max_steps:
            log_entry["stop_reason"] = "max_steps"
        _write_log(log_entry, selected_log_path)

        if safety_block:
            return {
                "result": result,
                "stop_reason": "safety_block",
                "steps": step,
                "tool_calls": tool_call_count,
                "run_id": run_id,
            }
        if step == max_steps:
            return {
                "result": result,
                "stop_reason": "max_steps",
                "steps": step,
                "tool_calls": tool_call_count,
                "run_id": run_id,
            }
        messages.append(
            {
                "role": "tool",
                "content": result_text,
            }
        )

    return {
        "result": None,
        "stop_reason": "max_steps",
        "steps": max_steps,
        "tool_calls": tool_call_count,
        "run_id": run_id,
    }


if __name__ == "__main__":
    print(json.dumps(run_agent("Count transit incidents by route."), indent=2))
