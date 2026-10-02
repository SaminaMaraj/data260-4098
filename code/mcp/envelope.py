"""Shared response envelope for the transit MCP tools and Part 4."""

from typing import Any


def tool_envelope(
    data: Any = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Return the one response shape used by every domain tool."""
    return {
        "ok": error is None,
        "data": data if error is None else None,
        "error": error,
    }
