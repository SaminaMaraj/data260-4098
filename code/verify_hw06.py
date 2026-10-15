"""Objective HW6 smoke checks for the tagged repository state."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
PORT = 8498
BASE_URL = f"http://127.0.0.1:{PORT}"


def request_json(path: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict | list]:
    data = json.dumps(body).encode() if body is not None else None
    request = Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=5) as response:
        raw = response.read().decode()
        return response.status, json.loads(raw) if raw else {}


def main() -> int:
    checks: list[dict] = []
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "SESSION_HTTPS_ONLY": "0"},
    )
    try:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                status, health = request_json("/health")
                if status == 200:
                    break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError("FastAPI did not start on port 8498")

        checks.append({"name": "FastAPI health", "passed": status == 200 and health.get("status") == "ok"})
        openapi_status, openapi = request_json("/openapi.json")
        paths = openapi.get("paths", {}) if isinstance(openapi, dict) else {}
        checks.append({"name": "HW6 routes registered", "passed": openapi_status == 200 and "/api/chat" in paths and "/api/mongo/incidents" in paths})

        try:
            request_json("/api/mongo/incidents", method="POST", body={"category": "delay"})
            validation_passed = False
        except Exception as exc:
            validation_passed = "HTTP Error 422" in str(exc)
        checks.append({"name": "Mongo Pydantic validation rejects missing fields", "passed": validation_passed})

        required_files = [
            "AGENT.md",
            "MEMORY.md",
            "memory_probes.yaml",
            "src/mongo_api.py",
            "src/hw6_memory.py",
            "src/file_memory.py",
            "code/verify_agent_instruction.py",
        ]
        checks.append({"name": "Required HW6 files exist", "passed": all((ROOT / item).exists() for item in required_files)})
    except Exception as exc:
        checks.append({"name": "verification runner", "passed": False, "detail": str(exc)})
    finally:
        process.terminate()
        process.wait(timeout=5)

    result = {
        "homework": 6,
        "SID4": 4098,
        "PORT_BASE": PORT,
        "PREFIX": "s4098",
        "SEED": 4098,
        "VERIFY_SEED": 264098,
        "model": os.environ.get("SMOL_MODEL", "qwen3:8b"),
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
    }
    output = ROOT / "reports" / "hw06" / "verification.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

