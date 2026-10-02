"""Safe single entry point for the three transit domain tools."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any, Callable


MCP_DIR = Path(__file__).resolve().parent
REPO_ROOT = MCP_DIR.parents[1]
# Prevent code/mcp from shadowing the external mcp package during imports.
sys.path[:] = [
    x
    for x in sys.path
    if Path(x or ".").resolve() != Path(__file__).resolve().parent
]
sys.path.insert(0, str(MCP_DIR))

from envelope import tool_envelope


ToolFunction = Callable[..., dict[str, Any]]
ToolRegistry = dict[str, ToolFunction]

_injected_registry: ToolRegistry | None = None


def configure_tool_registry(registry: ToolRegistry | None) -> None:
    """Install an in-memory registry for offline tests or controlled demos."""
    global _injected_registry
    _injected_registry = registry


def _real_registry() -> ToolRegistry:
    """Load the transit server lazily so offline tests need no MCP/database."""
    code_dir = REPO_ROOT / "code"
    sys.path[:] = [
        x
        for x in sys.path
        if Path(x or ".").resolve() != code_dir.resolve()
    ]
    importlib.import_module("mcp")
    if str(MCP_DIR) not in sys.path:
        sys.path.insert(0, str(MCP_DIR))
    transit = importlib.import_module("transit_server")
    return {
        "search_incidents": transit.search_incidents,
        "get_incident": transit.get_incident,
        "incident_count_by_route": transit.incident_count_by_route,
    }


def _unknown_fields(inputs: dict[str, Any], allowed: set[str]) -> list[str]:
    return sorted(set(inputs) - allowed)


def _validate_search(inputs: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    allowed = {"query", "category", "limit"}
    extra = _unknown_fields(inputs, allowed)
    if extra:
        return None, f"unexpected input field(s): {', '.join(extra)}"
    if "query" not in inputs:
        return None, "missing required input: query"
    if not isinstance(inputs["query"], str) or not inputs["query"].strip():
        return None, "query must be a non-empty string"

    category = inputs.get("category")
    if category is not None and not isinstance(category, str):
        return None, "category must be a string or null"

    limit = inputs.get("limit", 10)
    if isinstance(limit, bool) or not isinstance(limit, int):
        return None, "limit must be an integer"
    if limit < 1:
        return None, "limit must be at least 1"
    return {
        "query": inputs["query"],
        "category": category,
        "limit": limit,
    }, None


def _validate_get(inputs: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    extra = _unknown_fields(inputs, {"incident_code"})
    if extra:
        return None, f"unexpected input field(s): {', '.join(extra)}"
    if "incident_code" not in inputs:
        return None, "missing required input: incident_code"
    if not isinstance(inputs["incident_code"], str):
        return None, "incident_code must be a string"
    return {"incident_code": inputs["incident_code"]}, None


def _validate_aggregate(
    inputs: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    extra = _unknown_fields(inputs, {"min_incidents"})
    if extra:
        return None, f"unexpected input field(s): {', '.join(extra)}"
    minimum = inputs.get("min_incidents", 0)
    if isinstance(minimum, bool) or not isinstance(minimum, int):
        return None, "min_incidents must be an integer"
    if minimum < 0:
        return None, "min_incidents must be greater than or equal to 0"
    return {"min_incidents": minimum}, None


def _validated_inputs(
    name: str,
    inputs: Any,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(inputs, dict):
        return None, "inputs must be a JSON object"
    if name == "search_incidents":
        return _validate_search(inputs)
    if name == "get_incident":
        return _validate_get(inputs)
    if name == "incident_count_by_route":
        return _validate_aggregate(inputs)
    return None, f"unknown tool name: {name}"


def execute_tool(name, inputs):
    """Validate, dispatch, and JSON-encode one domain-tool call.

    This function deliberately catches every normal application exception and
    always returns a JSON string containing the shared response envelope.
    """
    try:
        validated, validation_error = _validated_inputs(name, inputs)
        if validation_error:
            return json.dumps(tool_envelope(error=validation_error))

        # Safety rule: prevent bulk extraction through the single tool entry
        # point while leaving the domain tool's normal limit of 50 unchanged.
        if name == "search_incidents" and validated["limit"] > 50:
            return json.dumps(
                tool_envelope(
                    error="safety policy: search limit cannot exceed 50"
                )
            )

        registry = _injected_registry or _real_registry()
        function = registry.get(name)
        if function is None:
            return json.dumps(tool_envelope(error=f"unknown tool name: {name}"))

        result = function(**validated)
        if not isinstance(result, dict):
            return json.dumps(
                tool_envelope(error="tool returned a non-object result")
            )
        if set(result) != {"ok", "data", "error"}:
            return json.dumps(
                tool_envelope(error="tool returned an invalid response envelope")
            )
        return json.dumps(result)
    except Exception as exc:
        return json.dumps(tool_envelope(error=f"tool execution failed: {exc}"))
