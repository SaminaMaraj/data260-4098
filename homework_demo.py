"""HW8 Part 1 demo: CREATE_INCIDENT -> GET_INCIDENT through FastAPI + Kafka.

    python homework_demo.py                  (stack from docker-compose.hw8.yml running)

The client creates each correlation_id once and sends it with the request; the
API wrapper, the worker and the response keep it unchanged. At the end the
worker and API container logs are merged with the client log by timestamp, so
the whole send -> receive -> process -> reply -> client sequence is one excerpt.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.hw8_kafka.config import (  # noqa: E402
    PORT_BASE,
    REQUEST_TOPIC,
    RESPONSE_TOPIC,
    banner,
    log,
    now_iso,
)

C = "CLIENT"
API = f"http://127.0.0.1:{PORT_BASE}/incidents/kafka"
RAW = ROOT / "reports" / "hw08" / "raw"
CLIENT_LINES: list[str] = []
TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z) \[")

INCIDENT = {
    "incidentTitle": "Bus collision at Diridon Station",
    "routeLine": "VTA Route 22",
    "submitterEmail": "kazisaminamaraj.mumu@sjsu.edu",
    "description": "A Route 22 bus hit a parked car while leaving Diridon Station; "
    "no injuries, the bus was taken out of service.",
    "category": "collision",
    "termsAccepted": True,
    "passengersAffected": 18,
}


def clog(message: str) -> None:
    line = f"{now_iso()} [{C}] {message}"
    CLIENT_LINES.append(line)
    print(line, flush=True)


def post(body: dict) -> dict:
    request = Request(
        API,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode())


def call(step: str, operation: str, data: dict) -> tuple[str, dict]:
    cid = str(uuid.uuid4())  # created once, here, by the client
    clog(f"{step} correlation_id created: {cid}")
    body = {"correlation_id": cid, "operation": operation, "data": data}
    clog(
        f"{step} SEND {operation} correlation_id={cid} via {API} -> Kafka topic "
        f"{REQUEST_TOPIC} (reply_to={RESPONSE_TOPIC})"
    )
    clog(f"{step} request body={json.dumps(body)}")
    response = post(body)
    clog(f"{step} RESPONSE received by client: {json.dumps(response)}")
    same = response.get("correlation_id") == cid
    clog(f"{step} correlation_id preserved: {same} ({response.get('correlation_id')})")
    if not same:
        raise SystemExit("correlation_id changed on the way - this must not happen")
    return cid, response


def container_lines(name: str, since: str) -> list[str]:
    try:
        out = subprocess.run(
            ["docker", "logs", "--since", since, name],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return (out.stdout + out.stderr).splitlines()
    except (OSError, subprocess.SubprocessError):
        return []


def merged_sequence(cids: list[str], since: str, log_files: list[str]) -> list[str]:
    lines = list(CLIENT_LINES)
    if log_files:
        for path in log_files:
            lines += Path(path).read_text().splitlines()
    else:
        for name in ("s4098-incident-api", "s4098-incident-worker"):
            lines += container_lines(name, since)
    keep = [
        ln for ln in dict.fromkeys(lines) if TS.match(ln) and any(c in ln for c in cids)
    ]

    # Several lines often share one millisecond, so lines are ordered by the
    # operation (CREATE, then GET) and the stage of the request, then by time.
    def sort_key(line):
        found = [i for i, c in enumerate(cids) if c in line]
        group = found[0] if len(found) == 1 else len(cids)
        stage = next(
            (rank for rank, pat in enumerate(STAGES) if pat in line), len(STAGES)
        )
        return (group, stage, TS.match(line).group(1))

    return sorted(keep, key=sort_key)


# causal order of one request/response round trip
STAGES = [
    "[CLIENT] [CREATE] correlation_id created",
    "[CLIENT] [GET] correlation_id created",
    "] SEND CREATE_INCIDENT",
    "] SEND GET_INCIDENT",
    "] request body=",
    "[API] HTTP POST",
    "[API] SEND to topic",
    "[API] SEND request",
    "[WORKER] RECEIVE topic",
    "[WORKER] RECEIVE request",
    "[WORKER] PROCESS operation",
    "[WORKER] PROCESS done",
    "[WORKER] DUPLICATE",
    "[WORKER] REPLY sent",
    "[WORKER] REPLY response",
    "[API] RESPONSE received",
    "[API] RETURN HTTP",
    "] RESPONSE received by client",
    "correlation_id preserved:",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--log-files", nargs="*", default=[], help="merge these instead of docker logs"
    )
    args = parser.parse_args()

    banner("homework_demo.py (Part 1)")
    since = now_iso()

    print("\n=== Steps 1-7: CREATE_INCIDENT ===")
    create_cid, created = call("[CREATE]", "CREATE_INCIDENT", INCIDENT)
    if not created.get("success"):
        raise SystemExit(f"CREATE failed: {created}")
    incident_id = created["incident_id"]
    clog(
        f"[CREATE] extracted generated incident_id={incident_id} "
        f"(correlation_id={create_cid})"
    )

    print("\n=== Steps 8-9: GET_INCIDENT ===")
    get_cid, fetched = call("[GET]", "GET_INCIDENT", {"incident_id": incident_id})

    print("\n=== Step 10: retrieved incident ===")
    print(json.dumps(fetched.get("incident"), indent=2))
    ok = (
        fetched.get("success") is True
        and fetched["incident"]["incident_id"] == incident_id
        and all(
            fetched["incident"][k] == v
            for k, v in INCIDENT.items()
            if k != "description"
        )
    )
    clog(f"[GET] round trip matches the created incident: {ok}")
    clog(
        f"[DONE] correlation_id preserved for both operations: "
        f"CREATE={create_cid} GET={get_cid}"
    )

    print("\n=== Full sequence (client + API + worker logs, ordered by time) ===")
    sequence = merged_sequence([create_cid, get_cid], since, args.log_files)
    for line in sequence:
        print(line)

    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "part1_sequence.log").write_text("\n".join(sequence) + "\n")
    (RAW / "part1_demo.json").write_text(
        json.dumps(
            {
                "create": {
                    "correlation_id": create_cid,
                    "request": INCIDENT,
                    "response": created,
                },
                "get": {"correlation_id": get_cid, "response": fetched},
                "round_trip_ok": ok,
            },
            indent=2,
        )
    )
    log(C, f"saved {RAW / 'part1_sequence.log'} and part1_demo.json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
