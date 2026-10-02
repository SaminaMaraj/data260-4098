"""HW5 smoke verification for the running API, MCP servers, and evidence."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


CODE_DIR = Path(__file__).resolve().parent
MCP_DIR = CODE_DIR / "mcp"
REPO_ROOT = CODE_DIR.parent
# Remove code/ because running this file would otherwise shadow installed mcp.
sys.path[:] = [
    item
    for item in sys.path
    if Path(item or ".").resolve() != CODE_DIR.resolve()
]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(MCP_DIR))

from envelope import tool_envelope


REPORT_DIR = REPO_ROOT / "reports" / "hw05"
VERIFICATION_PATH = REPORT_DIR / "verification.json"
PYTHON = Path(sys.executable)

REQUIRED_FILES = [
    "RUN_LOG.txt",
    "CONTRACTS.md",
    "METRICS.md",
    "AI_USE.md",
    "REFLECTION.md",
    "verification.json",
    "report.pdf",
    "raw/fault_injection.csv",
    "raw/agent_runs.jsonl",
    "raw/inspector/search_meals_by_name_valid.json",
    "raw/inspector/meals_by_ingredient_valid.json",
    "raw/inspector/meal_details_valid.json",
    "raw/inspector/random_meal_valid.json",
    "raw/inspector/search_incidents_valid.json",
    "raw/inspector/get_incident_valid.json",
    "raw/inspector/incident_count_by_route_valid.json",
    "raw/inspector/search_incidents_invalid.json",
    "raw/inspector/get_incident_invalid.json",
    "raw/inspector/incident_count_by_route_invalid.json",
]


def _check(name: str, function) -> dict[str, Any]:
    try:
        detail = function()
        return {"name": name, "passed": True, "detail": detail}
    except Exception as exc:
        return {"name": name, "passed": False, "detail": str(exc)}


def _git_hash() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _health_check() -> str:
    response = httpx.get("http://localhost:8498/health", timeout=10.0)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "ok":
        raise RuntimeError(f"unexpected health response: {payload}")
    return f"HTTP {response.status_code}; record_count={payload.get('record_count')}"


async def _call_mcp_server(server_path: Path, tool_name: str, arguments: dict) -> str:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_parameters = StdioServerParameters(
        command=str(PYTHON),
        args=[str(server_path)],
        cwd=str(REPO_ROOT),
    )
    async with stdio_client(server_parameters) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)
            if getattr(result, "isError", False):
                raise RuntimeError(f"{tool_name} returned an MCP error")
            return f"{server_path.name}:{tool_name} answered"


def _mcp_check(server_name: str, tool_name: str, arguments: dict) -> str:
    server_path = MCP_DIR / server_name
    return asyncio.run(_call_mcp_server(server_path, tool_name, arguments))


def _offline_tests() -> str:
    completed = subprocess.run(
        [str(PYTHON), "tests/run_tests.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stdout + completed.stderr)
    return completed.stdout.strip().splitlines()[-1]


def _required_files() -> str:
    missing = [item for item in REQUIRED_FILES if not (REPORT_DIR / item).is_file()]
    if missing:
        raise FileNotFoundError(", ".join(missing))
    return f"{len(REQUIRED_FILES)} required files present"


def main() -> int:
    checks = [
        _check("FastAPI health on port 8498", _health_check),
        _check(
            "meals MCP stdio tool call",
            lambda: _mcp_check(
                "meals_server.py",
                "search_meals_by_name",
                {"query": "pasta", "limit": 1},
            ),
        ),
        _check(
            "transit MCP stdio tool call",
            lambda: _mcp_check(
                "transit_server.py",
                "incident_count_by_route",
                {"min_incidents": 0},
            ),
        ),
        _check("offline tests", _offline_tests),
        _check("required HW5 report files", _required_files),
    ]

    try:
        commit_hash = _git_hash()
    except Exception as exc:
        commit_hash = "unavailable"
        checks.append(
            {"name": "git commit hash", "passed": False, "detail": str(exc)}
        )
    else:
        checks.append(
            {"name": "git commit hash", "passed": bool(commit_hash), "detail": commit_hash}
        )

    verification = {
        "homework": 5,
        "SID4": 4098,
        "commit_hash": commit_hash,
        "model": "qwen3:8b",
        "configuration": {
            "ollama_base_url": "http://localhost:11434",
            "api_url": "http://localhost:8498",
        },
        "SEED": 4098,
        "VERIFY_SEED": 264098,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    VERIFICATION_PATH.write_text(
        json.dumps(verification, indent=2) + "\n",
        encoding="utf-8",
    )

    for check in checks:
        print(f"{'PASS' if check['passed'] else 'FAIL'} {check['name']}: {check['detail']}")
    print(f"verification.json: {VERIFICATION_PATH}")
    return 0 if verification["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
