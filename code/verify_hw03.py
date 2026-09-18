"""Objective smoke checks for DATA 260 Homework 3."""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Make imports work when the script is invoked as `python code/verify_hw03.py`.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient

import src.auth as auth
from src.api import app


REPORT_DIR = REPO_ROOT / "reports" / "hw03"
OUTPUT_PATH = REPORT_DIR / "verification.json"

REQUIRED_FILES = [
    REPO_ROOT / "src" / "auth.py",
    REPO_ROOT / "templates" / "base.html",
    REPO_ROOT / "templates" / "home.html",
    REPO_ROOT / "templates" / "login.html",
    REPO_ROOT / "templates" / "dashboard.html",
]


def check_required_files() -> dict:
    missing = [str(path.relative_to(REPO_ROOT)) for path in REQUIRED_FILES if not path.exists()]
    if missing:
        raise AssertionError(f"Missing required files: {missing}")
    return {"file_count": len(REQUIRED_FILES), "missing": []}


def check_authentication() -> dict:
    # HTTPS is intentional: the assignment requires a secure session cookie.
    client = TestClient(app, base_url="https://testserver")

    home = client.get("/")
    login_page = client.get("/login")
    incidents = client.get("/incidents")
    protected_before_login = client.get("/dashboard", follow_redirects=False)
    if home.status_code != 200 or login_page.status_code != 200 or incidents.status_code != 200:
        raise AssertionError("A required public page did not return HTTP 200")
    if protected_before_login.status_code != 303:
        raise AssertionError("Dashboard was accessible without a session")

    invalid = client.post("/login", data={"username": "wrong", "password": "wrong"})
    if invalid.status_code != 401 or "Invalid username or password" not in invalid.text:
        raise AssertionError("Invalid credentials did not produce the required alert")

    login = client.post(
        "/login",
        data={"username": "samina", "password": "Transit4098!"},
        follow_redirects=False,
    )
    cookie = login.headers.get("set-cookie", "").lower()
    required_cookie_flags = ["secure", "httponly", "samesite=lax"]
    if login.status_code != 303 or login.headers.get("location") != "/dashboard":
        raise AssertionError("Valid credentials did not redirect to the dashboard")
    if any(flag not in cookie for flag in required_cookie_flags):
        raise AssertionError(f"Secure cookie flags missing from Set-Cookie: {cookie}")
    if client.get("/dashboard").status_code != 200:
        raise AssertionError("Authenticated user could not reach the dashboard")

    client.get("/logout", follow_redirects=False)
    after_logout = client.get("/dashboard", follow_redirects=False)
    if after_logout.status_code != 303:
        raise AssertionError("Logged-out session still reached the dashboard")

    timeout_client = TestClient(app, base_url="https://timeout-testserver")
    timeout_client.post("/login", data={"username": "samina", "password": "Transit4098!"})
    real_time = auth.time.time
    try:
        auth.time.time = lambda: real_time() + auth.IDLE_TIMEOUT_SECONDS + 1
        expired = timeout_client.get("/dashboard", follow_redirects=False)
    finally:
        auth.time.time = real_time
    if expired.status_code != 303:
        raise AssertionError("Expired session still reached the dashboard")

    return {
        "public_pages": {"home": home.status_code, "login": login_page.status_code, "incidents": incidents.status_code},
        "protected_before_login": protected_before_login.status_code,
        "invalid_login": invalid.status_code,
        "successful_login": login.status_code,
        "dashboard_after_login": 200,
        "cookie_flags": required_cookie_flags,
        "logout_dashboard": after_logout.status_code,
        "expired_dashboard": expired.status_code,
    }


def current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    checks = {
        "required_files": check_required_files(),
        "authentication": check_authentication(),
    }
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "commit": current_commit(),
        "checks": checks,
    }
    OUTPUT_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - command-line failure path
        failure = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "status": "FAIL",
            "error": str(exc),
        }
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(failure, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(failure, indent=2))
        sys.exit(1)
