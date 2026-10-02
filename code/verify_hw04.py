import datetime as dt
import json
import os
import subprocess
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8498"
OUTPUT = Path("reports/hw04/verification.json")

checks = []
DEMO_PASSWORD = os.environ["HW4_DEMO_PASSWORD"]


def add_check(name, passed, details):
    checks.append(
        {
            "name": name,
            "pass": bool(passed),
            "details": details,
        }
    )


session = requests.Session()

try:
    response = session.get(f"{BASE_URL}/health", timeout=10)
    data = response.json()

    add_check(
        "health_endpoint",
        response.status_code == 200 and data.get("status") == "ok",
        data,
    )

    add_check(
        "mysql_record_count",
        data.get("record_count", 0) >= 5000,
        {"record_count": data.get("record_count")},
    )

    login = session.post(
        f"{BASE_URL}/api/hw4/auth/login",
        json={
            "email": "samina.hw4@example.com",
            "password": DEMO_PASSWORD,
        },
        timeout=10,
    )

    add_check(
        "login",
        login.status_code == 200,
        {"status_code": login.status_code},
    )

    incidents = session.get(
        f"{BASE_URL}/api/hw4/incidents",
        params={"limit": 1},
        timeout=10,
    )

    add_check(
        "protected_incident_list",
        incidents.status_code == 200
        and isinstance(incidents.json(), list)
        and len(incidents.json()) >= 1,
        {"status_code": incidents.status_code},
    )

except Exception as exc:
    add_check("smoke_test_execution", False, {"error": str(exc)})


commit = subprocess.check_output(
    ["git", "rev-parse", "HEAD"],
    text=True,
).strip()

result = {
    "homework": "DATA260 HW4",
    "sid4": 4098,
    "commit": commit,
    "configuration": {
        "port": 8498,
        "prefix": "s4098",
        "database": "s4098_rel",
        "seed": 4098,
        "verify_seed": 264098,
    },
    "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
    "checks": checks,
}

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
