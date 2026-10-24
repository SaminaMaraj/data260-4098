"""Objective HW7 smoke checks for the tagged repository state.

    make verify-hw07      (MySQL container + Ollama running, .env loaded)

Starts FastAPI on PORT_BASE 8498, checks behavior (status codes, not wording),
runs one hand-written agent task, the offline test suites, and writes
reports/hw07/verification.json. It creates one temporary incident and deletes
it again; it never modifies application code.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
PORT = 8498
BASE_URL = f"http://127.0.0.1:{PORT}"
SID4, VERIFY_SEED = 4098, 264098
TEST_CODE = f"INC-{VERIFY_SEED:06d}"  # INC-264098, derived from VERIFY_SEED

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def call(path, method="GET", body=None, token=None, timeout=10):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = Request(BASE_URL + path, data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def login(role):
    password = os.environ.get(f"HW7_{role.upper()}_PASSWORD", "")
    status, body = call(
        "/auth/login", "POST", {"username": f"s4098_{role}", "password": password}
    )
    return status, body.get("access_token")


def run_script(*args, timeout=600):
    completed = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    tail = (completed.stdout.strip().splitlines() or [""])[-1]
    return completed.returncode == 0, tail


CODE_TREES = ("src", "code", "tests", "frontend")


def git_state() -> dict:
    """The exact state that was tested: HEAD, local changes, code tree hashes.

    The tree hashes let anyone confirm later that a report-only commit (e.g.
    the one that adds the PDF) contains exactly the same code that was tested:
    git rev-parse <commit>:src must print the same hash.
    """

    def run(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    try:
        dirty = [
            line[3:]
            for line in run("status", "--porcelain").splitlines()
            if not line[3:].startswith("reports/")
        ]
        return {
            "commit": run("rev-parse", "HEAD"),
            "uncommitted_code_changes": dirty,
            "code_tree_hashes": {d: run("rev-parse", f"HEAD:{d}") for d in CODE_TREES},
        }
    except Exception as exc:  # noqa: BLE001
        return {"commit": "unknown", "error": str(exc)}


def main() -> int:
    checks: list[dict] = []

    def check(name, passed, detail=""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
        print(f"{'PASS' if passed else 'FAIL'} {name} {detail}")

    git = git_state()
    commit = git["commit"]

    print("Kazi Samina Maraj Mumu | make verify-hw07")
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "src.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={**os.environ, "SESSION_HTTPS_ONLY": "0", "PYTHONPATH": str(ROOT)},
    )
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                if call("/health")[0] == 200:
                    break
            except Exception:
                time.sleep(0.3)
        else:
            raise RuntimeError(f"FastAPI did not start on port {PORT}")

        # ---- Part 1: JWT + RBAC -------------------------------------------
        status, reader = login("reader")
        check("login valid credentials -> 200 + JWT", status == 200 and reader)
        status, _ = call(
            "/auth/login",
            "POST",
            {"username": "s4098_reader", "password": "wrong-password"},
        )
        check("login invalid credentials -> 401", status == 401)
        check("GET /auth/me without token -> 401", call("/auth/me")[0] == 401)
        check(
            "GET /auth/me invalid token -> 401",
            call("/auth/me", token="invalid.token.value")[0] == 401,
        )
        status, me = call("/auth/me", token=reader)
        check(
            "GET /auth/me valid token -> identity + role",
            status == 200 and me.get("role") == "reader",
        )
        check(
            "list incidents with reader token -> 200",
            call("/api/hw4/incidents?limit=5", token=reader)[0] == 200,
        )

        _, writer = login("writer")
        _, moderator = login("moderator")
        routes = call("/api/hw4/routes?limit=1", token=reader)[1]
        payload = {
            "incidentCode": TEST_CODE,
            "incidentTitle": "HW7 verify temporary incident",
            "routeLine": routes[0]["routeName"] if routes else "VTA Route 22",
            "routeId": routes[0]["id"] if routes else None,
            "submitterEmail": "verify@example.com",
            "description": "Temporary record created and deleted by verify_hw07.",
            "category": "delay",
            "passengersAffected": 0,
            "termsAccepted": True,
        }
        check(
            "create with reader -> 403",
            call("/api/hw4/incidents", "POST", payload, reader)[0] == 403,
        )
        status, created = call("/api/hw4/incidents", "POST", payload, writer)
        check("create with writer -> 201", status == 201)
        if status == 201:
            url = f"/api/hw4/incidents/{created['id']}"
            check(
                "delete with writer -> 403", call(url, "DELETE", token=writer)[0] == 403
            )
            check(
                "delete with moderator -> 200",
                call(url, "DELETE", token=moderator)[0] == 200,
            )
    except Exception as exc:
        check("verification runner", False, str(exc))
    finally:
        server.terminate()
        server.wait(timeout=10)

    # ---- Part 2: hand-written agent loop completes a task -----------------
    try:
        sys.path.insert(0, str(ROOT / "code" / "mcp"))
        from agent_loop import run_agent
        from hw07_tasks import TASKS, verify

        run = run_agent(TASKS["A"]["prompt"], temperature=0.0, log=None)
        result = verify("A", run)
        check(
            "agent loop completes verification task A",
            result["passed"],
            f"stop={run['stop_reason']} tool_calls={run['tool_calls']}",
        )
    except Exception as exc:
        check("agent loop completes verification task A", False, str(exc))

    # ---- Offline suites (Parts 1-6 logic, no model) -----------------------
    for name, script in [
        ("offline auth/RBAC tests", "tests/test_hw07_auth.py"),
        ("offline agent/reflexion tests", "tests/test_hw07_agent.py"),
        (
            "offline tool tests (csv_sql read-only, calculator, gate)",
            "tests/test_hw07_tools.py",
        ),
        (
            "offline Part 4 validator tests (reference prices, costs, bounded round)",
            "tests/test_hw07_bikeshare_check.py",
        ),
    ]:
        passed, tail = run_script(script)
        check(name, passed, tail)

    # ---- Part 4 saved final runs: validated, >= 500 rows, expected winner ----
    for label, winner in [
        ("scenario_A", "Buy Monthly Membership"),
        ("scenario_B", "Pay Per Ride/Minute"),
    ]:
        path = ROOT / "reports" / "hw07" / "raw" / "bikeshare" / label / "run.json"
        try:
            run = json.loads(path.read_text(encoding="utf-8"))
            ok = (
                run["validated"]
                and run["decision"] == winner
                and run["trip_stats"]["rows_loaded"] >= 500
            )
            detail = (
                f"decision={run['decision']} "
                f"validation={run['validation'].get('status', run['validated'])} "
                f"rows={run['trip_stats']['rows_loaded']} "
                f"stop={run['metrics']['stop_reason']}"
            )
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        check(f"Part 4 saved {label} run validated", ok, detail)

    required = [
        "reports/hw07/RUN_LOG.txt",
        "reports/hw07/METRICS.md",
        "reports/hw07/AI_USE.md",
        "reports/hw07/raw/reliability_attempts.csv",
        "reports/hw07/raw/reflexion_comparison.csv",
        "reports/hw07/raw/attacks.json",
        "reports/hw07/raw/tool_boundary_test.json",
        "reports/hw07/raw/bikeshare/scenario_A/run.json",
        "reports/hw07/raw/bikeshare/scenario_B/run.json",
        "reports/hw07/raw/bikeshare/scenario_A/pricing_snapshot.txt",
        "reports/hw07/raw/bikeshare/scenario_B/pricing_snapshot.txt",
        "reports/hw07/raw/scenarios/scenario_summaries.json",
        "reports/hw07/raw/safety_gate_results.csv",
        "reports/hw07/fixtures/hostile_override.html",
        ".pre-commit-config.yaml",
        "pyproject.toml",
    ]
    missing = [p for p in required if not (ROOT / p).exists()]
    check(
        "required HW7 files exist", not missing, f"missing={missing}" if missing else ""
    )

    result = {
        "homework": 7,
        "SID4": SID4,
        "PORT_BASE": PORT,
        "PREFIX": "s4098",
        "SEED": 4098,
        "VERIFY_SEED": VERIFY_SEED,
        "DOMAIN_ID": 2,
        "commit_hash": commit,
        "tested_state": git,
        "model": os.environ.get("SMOL_MODEL", "qwen3:8b"),
        "model_settings": {"temperature": 0.0, "max_iterations": 8, "max_repairs": 2},
        "checks": checks,
        "passed": all(c["passed"] for c in checks),
    }
    out = ROOT / "reports" / "hw07" / "verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"\n{sum(c['passed'] for c in checks)}/{len(checks)} checks passed -> {out}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
