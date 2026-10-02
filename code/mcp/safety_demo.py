"""Tiny demonstration of one allowed and one safety-blocked call."""

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

from execute_tool import execute_tool


def main():
    calls = [
        (
            "allowed",
            "search_incidents",
            {"query": "delay", "limit": 10},
        ),
        (
            "blocked",
            "search_incidents",
            {"query": "delay", "limit": 51},
        ),
    ]
    for label, name, inputs in calls:
        print(label, execute_tool(name, inputs))


if __name__ == "__main__":
    main()
