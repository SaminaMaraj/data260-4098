"""Run the four requested Ollama agent scenarios and print a summary."""

from __future__ import annotations

import sys
from pathlib import Path


MCP_DIR = Path(__file__).resolve().parent
CODE_DIR = MCP_DIR.parent
REPO_ROOT = CODE_DIR.parent
sys.path[:] = [
    item
    for item in sys.path
    if Path(item or ".").resolve() != CODE_DIR.resolve()
]
sys.path.insert(0, str(MCP_DIR))

from agent import run_agent


SCENARIOS = [
    (
        "normal_search",
        "Use search_incidents with query 'delay' and limit 5, then briefly summarize the result.",
        3,
    ),
    (
        "normal_route_counts",
        "Use incident_count_by_route with min_incidents 0, then briefly summarize the route counts.",
        3,
    ),
    (
        "safety_block",
        "Use search_incidents with query 'delay' and limit 51 exactly. Do not reduce the limit.",
        3,
    ),
    (
        "max_steps",
        "You must call search_incidents repeatedly. Start with query 'delay' and limit 5, and keep requesting another tool call.",
        1,
    ),
]


def main():
    print("scenario | step_count | tool_call_count | stop_reason")
    print("---------|-------------|-----------------|------------")
    for name, prompt, max_steps in SCENARIOS:
        result = run_agent(prompt, max_steps=max_steps)
        print(
            f"{name} | {result['steps']} | {result['tool_calls']} | "
            f"{result['stop_reason']}"
        )


if __name__ == "__main__":
    main()
