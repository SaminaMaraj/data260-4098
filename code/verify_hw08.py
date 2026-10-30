"""Objective HW8 smoke checks for the tagged repository state.

    make verify-hw08        (docker compose -f docker-compose.hw8.yml up -d first)

Checks behavior, not wording: topics, the FastAPI -> Kafka -> worker round
trip, error responses, a direct Kafka round trip, idempotent replay, the
three-agent pipeline, retry + dead-letter, key -> partition stability and the
offline tests. The agents run with the stub LLM in their own consumer groups
and a 'verify' experiment tag, so the check needs no Ollama and never touches
the normal pipeline. Temporary logs go to a temp folder; application code is
never modified. Writes reports/hw08/verification.json.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiokafka.admin import AIOKafkaAdminClient  # noqa: E402

from src.hw8_kafka.config import (  # noqa: E402
    DEAD_LETTER_TOPIC,
    DOMAIN_ID,
    DRAFTS_TOPIC,
    FINAL_TOPIC,
    INBOX_TOPIC,
    KAFKA_BOOTSTRAP,
    PORT_BASE,
    PREFIX,
    REQUEST_TOPIC,
    RESPONSE_TOPIC,
    SEED,
    SID4,
    STUDENT_NAME,
    TASKS_TOPIC,
    TOPICS,
    VERIFY_SEED,
)
from src.hw8_kafka.topics import encode, make_producer, tail_consumer  # noqa: E402

API = f"http://127.0.0.1:{PORT_BASE}"
CODE_TREES = ("src", "code", "tests")
INCIDENT = {
    "incidentTitle": f"Verify {VERIFY_SEED}",
    "routeLine": "VTA Route 22",
    "submitterEmail": "verify@example.com",
    "description": "Smoke-test incident created by make verify-hw08.",
    "category": "delay",
    "termsAccepted": True,
    "passengersAffected": 3,
}
CHECKS: list[dict] = []


def check(name: str, passed, detail: str = "") -> None:
    CHECKS.append({"name": name, "passed": bool(passed), "detail": detail})
    print(f"{'PASS' if passed else 'FAIL'} {name} {detail}".rstrip(), flush=True)


def git_state() -> dict:
    def run(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    try:
        dirty = [
            ln[3:]
            for ln in run("status", "--porcelain").splitlines()
            if not ln[3:].startswith("reports/")
        ]
        return {
            "commit": run("rev-parse", "HEAD"),
            "uncommitted_code_changes": dirty,
            "code_tree_hashes": {d: run("rev-parse", f"HEAD:{d}") for d in CODE_TREES},
        }
    except Exception as exc:  # noqa: BLE001
        return {"commit": "unknown", "error": str(exc)}


def http(path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = Request(
        API + path,
        data=data,
        method="POST" if body else "GET",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=30) as response:
        return response.status, json.loads(response.read().decode())


async def kafka_call(producer, replies, message: dict, wait: float = 10) -> list[dict]:
    await producer.send_and_wait(REQUEST_TOPIC, encode(message))
    found, deadline = [], time.monotonic() + wait
    while time.monotonic() < deadline and not found:
        for msgs in (await replies.getmany(timeout_ms=200)).values():
            for m in msgs:
                v = json.loads(m.value.decode())
                if v.get("correlation_id") == message["correlation_id"]:
                    found.append({"topic": m.topic, **v})
    return found


class Agents:
    """planner/writer/reviewer subprocesses with the stub LLM, verify-only groups."""

    def __init__(self, tmp: Path, tag: str):
        self.tmp, self.tag, self.procs = tmp, tag, {}

    def start(self, name: str, *extra: str):
        log = self.tmp / f"{name}.log"
        cmd = [
            sys.executable,
            "-u",
            str(ROOT / "code" / "hw8" / f"{name.split('-')[0]}.py"),
            "--instance",
            f"{name}-verify",
            "--group",
            f"{PREFIX}_verify_{name}_{self.tag}",
            "--experiment",
            f"verify-{self.tag}",
            "--offset-reset",
            "latest",
            "--llm",
            "stub",
            *extra,
        ]
        self.procs[name] = (
            subprocess.Popen(
                cmd, cwd=ROOT, stdout=log.open("w"), stderr=subprocess.STDOUT
            ),
            log,
        )

    def wait_ready(self, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if all("ASSIGNMENT" in log.read_text() for _, log in self.procs.values()):
                return True
            time.sleep(0.3)
        return False

    def stop(self):
        for proc, _ in self.procs.values():
            proc.terminate()
        for proc, _ in self.procs.values():
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                proc.kill()


async def collect(consumer, match, seconds) -> list[dict]:
    found, deadline = [], time.monotonic() + seconds
    while time.monotonic() < deadline:
        for msgs in (await consumer.getmany(timeout_ms=200)).values():
            for m in msgs:
                try:
                    v = json.loads(m.value.decode())
                except ValueError:
                    continue
                if match(v):
                    found.append({"partition": m.partition, **v})
        if found:
            return found
    return found


async def kafka_checks(tmp: Path) -> None:
    # 1 topics
    admin = AIOKafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP)
    await admin.start()
    described = {
        t["topic"]: len(t["partitions"])
        for t in await admin.describe_topics(list(TOPICS))
        if t.get("error_code", 0) == 0
    }
    await admin.close()
    check(
        "all 7 PREFIX topics exist with the planned partition counts",
        described == TOPICS,
        json.dumps(described),
    )
    check(f"{TASKS_TOPIC} has 2 partitions", described.get(TASKS_TOPIC) == 2)

    producer = await make_producer()
    replies = await tail_consumer(RESPONSE_TOPIC)

    # 2 direct Kafka round trip (no FastAPI in between)
    cid = str(uuid.uuid4())
    got = await kafka_call(
        producer,
        replies,
        {
            "correlation_id": cid,
            "reply_to": RESPONSE_TOPIC,
            "operation": "CREATE_INCIDENT",
            "data": INCIDENT,
        },
    )
    ok = got and got[0]["success"] and got[0]["topic"] == RESPONSE_TOPIC
    check(
        "direct Kafka CREATE_INCIDENT -> reply on reply_to with same correlation_id", ok
    )
    incident_id = got[0].get("incident_id") if got else None
    cid2 = str(uuid.uuid4())
    got2 = await kafka_call(
        producer,
        replies,
        {
            "correlation_id": cid2,
            "reply_to": RESPONSE_TOPIC,
            "operation": "GET_INCIDENT",
            "data": {"incident_id": incident_id},
        },
    )
    check(
        "direct Kafka GET_INCIDENT returns the created incident",
        got2
        and got2[0]["success"]
        and got2[0]["incident"]["incident_id"] == incident_id,
    )

    # 3 idempotent replay: same message twice -> same incident_id
    cid3 = str(uuid.uuid4())
    msg = {
        "correlation_id": cid3,
        "reply_to": RESPONSE_TOPIC,
        "operation": "CREATE_INCIDENT",
        "data": INCIDENT,
    }
    a = await kafka_call(producer, replies, msg)
    b = await kafka_call(producer, replies, msg)
    check(
        "replayed CREATE_INCIDENT (same correlation_id) creates no second incident",
        a and b and a[0].get("incident_id") == b[0].get("incident_id"),
        "requires the worker to run with HW8_IDEMPOTENCY=on",
    )
    await replies.stop()

    # 4 three-agent pipeline + poison/dead-letter with stub agents
    tag = time.strftime("%H%M%S")
    exp = f"verify-{tag}"
    agents = Agents(tmp, tag)
    for name in ("planner", "writer", "reviewer"):
        agents.start(name, "--backoff", "0.2")
    try:
        check(
            "planner, writer and reviewer start and join their groups",
            agents.wait_ready(),
        )
        final = await tail_consumer(FINAL_TOPIC)
        dead = await tail_consumer(DEAD_LETTER_TOPIC)
        drafts = await tail_consumer(DRAFTS_TOPIC)
        qid = str(uuid.uuid4())
        await producer.send_and_wait(
            INBOX_TOPIC,
            encode(
                {
                    "correlation_id": qid,
                    "experiment": exp,
                    "question": "What should riders be told when a bus route is "
                    "detoured?",
                }
            ),
            key=qid.encode(),
        )
        result = await collect(final, lambda v: v.get("correlation_id") == qid, 40)
        r = result[0] if result else {}
        stages = [(h["agent"], h["in_topic"]) for h in r.get("trace", [])]
        check(
            "question -> planner -> writer -> reviewer -> final keeps correlation_id",
            bool(result)
            and stages
            == [
                ("PLANNER", INBOX_TOPIC),
                ("WRITER", TASKS_TOPIC),
                ("REVIEWER", DRAFTS_TOPIC),
            ],
            json.dumps(stages),
        )
        check(
            "final message is JSON with status and answer",
            r.get("status") in ("approved", "needs_revision") and bool(r.get("answer")),
        )

        bad, good = str(uuid.uuid4()), str(uuid.uuid4())
        key = f"verify-{tag}".encode()
        await producer.send_and_wait(
            TASKS_TOPIC,
            encode({"correlation_id": bad, "experiment": exp, "plan": "<<corrupted>>"}),
            key=key,
        )
        await producer.send_and_wait(
            TASKS_TOPIC,
            encode(
                {
                    "correlation_id": good,
                    "experiment": exp,
                    "question": "q",
                    "plan": {"steps": ["answer"]},
                }
            ),
            key=key,
        )
        dl = await collect(dead, lambda v: v.get("correlation_id") == bad, 20)
        check(
            "poison task is retried 3 times, then moved to the dead-letter topic",
            bool(dl) and dl[0].get("attempts") == 3,
        )
        later = await collect(drafts, lambda v: v.get("correlation_id") == good, 20)
        check("message after the poison message is still processed", bool(later))
        for c in (final, dead, drafts):
            await c.stop()
    finally:
        agents.stop()

    # 5 partition key: every message for one incident lands in one partition
    sys.path.insert(0, str(ROOT / "code" / "hw8"))
    from run_failure_tests import ordering_messages  # the VERIFY_SEED incidents

    parts: dict[str, set] = {}
    for i, m in enumerate(ordering_messages()):
        incident = m["incident_id"]
        meta = await producer.send_and_wait(
            TASKS_TOPIC,
            encode(
                {
                    "correlation_id": str(uuid.uuid4()),
                    "experiment": f"verify-keys-{tag}",
                    "incident_id": incident,
                    "seq": i,
                }
            ),
            key=incident.encode(),
        )
        parts.setdefault(incident, set()).add(meta.partition)
    check(
        "keyed messages: one partition per incident key (20 VERIFY_SEED messages)",
        all(len(p) == 1 for p in parts.values()),
        json.dumps({k: sorted(v) for k, v in parts.items()}),
    )
    await producer.stop()


def main() -> int:
    print(
        f"{STUDENT_NAME} | make verify-hw08 | PREFIX={PREFIX} PORT_BASE={PORT_BASE}",
        flush=True,
    )
    git = git_state()

    # FastAPI wrapper (s4098-incident-api container)
    try:
        status, body = http("/health")
        check(f"FastAPI /health on port {PORT_BASE} -> 200", status == 200)
        cid = str(uuid.uuid4())
        _, created = http(
            "/incidents/kafka",
            {"correlation_id": cid, "operation": "CREATE_INCIDENT", "data": INCIDENT},
        )
        valid_uuid = False
        try:
            uuid.UUID(created.get("incident_id", ""))
            valid_uuid = True
        except ValueError:
            pass
        check(
            "API CREATE_INCIDENT -> success, UUID incident_id, same correlation_id",
            created.get("success") is True
            and valid_uuid
            and created.get("correlation_id") == cid,
        )
        gid = str(uuid.uuid4())
        _, fetched = http(
            "/incidents/kafka",
            {
                "correlation_id": gid,
                "operation": "GET_INCIDENT",
                "data": {"incident_id": created.get("incident_id")},
            },
        )
        inc = fetched.get("incident") or {}
        check(
            "API GET_INCIDENT round-trips every field",
            fetched.get("success") is True
            and fetched.get("correlation_id") == gid
            and all(inc.get(k) == v for k, v in INCIDENT.items()),
        )
        nid = str(uuid.uuid4())
        _, missing = http(
            "/incidents/kafka",
            {
                "correlation_id": nid,
                "operation": "GET_INCIDENT",
                "data": {"incident_id": str(uuid.uuid4())},
            },
        )
        check(
            "GET_INCIDENT unknown id -> success false + error + same correlation_id",
            missing.get("success") is False
            and missing.get("error")
            and missing.get("correlation_id") == nid,
        )
        uid = str(uuid.uuid4())
        _, unknown = http(
            "/incidents/kafka",
            {"correlation_id": uid, "operation": "DROP_TABLES", "data": {}},
        )
        check(
            "unknown operation -> success false + error + same correlation_id",
            unknown.get("success") is False
            and unknown.get("error")
            and unknown.get("correlation_id") == uid,
        )
        _, invalid = http(
            "/incidents/kafka",
            {
                "operation": "CREATE_INCIDENT",
                "data": {**INCIDENT, "submitterEmail": ""},
            },
        )
        check(
            "CREATE_INCIDENT with an empty required field -> success false",
            invalid.get("success") is False and invalid.get("error"),
        )
    except Exception as exc:  # noqa: BLE001
        check("FastAPI wrapper reachable", False, str(exc))

    with tempfile.TemporaryDirectory() as tmp:
        try:
            asyncio.run(kafka_checks(Path(tmp)))
        except Exception as exc:  # noqa: BLE001
            check("Kafka checks completed", False, f"{type(exc).__name__}: {exc}")

    tests = subprocess.run(
        [sys.executable, "tests/test_hw08.py"], cwd=ROOT, capture_output=True, text=True
    )
    tail = (tests.stdout.strip().splitlines() or [""])[-1]
    check("offline tests (tests/test_hw08.py)", tests.returncode == 0, tail)

    passed = sum(c["passed"] for c in CHECKS)
    report = {
        "homework": 8,
        "SID4": SID4,
        "PORT_BASE": PORT_BASE,
        "PREFIX": PREFIX,
        "SEED": SEED,
        "VERIFY_SEED": VERIFY_SEED,
        "DOMAIN_ID": DOMAIN_ID,
        "commit_hash": git.get("commit"),
        "tested_state": git,
        "model": "qwen3:8b via Ollama (Part 2 agents); this smoke test uses the stub "
        "LLM",
        "configuration": {
            "kafka": "apache/kafka:3.9.2, single KRaft broker, " + KAFKA_BOOTSTRAP,
            "topics": TOPICS,
            "agent_max_attempts": 3,
            "commit": "manual, after successful output",
        },
        "checks": CHECKS,
        "passed": passed,
        "total": len(CHECKS),
        "all_passed": passed == len(CHECKS),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    out = ROOT / "reports" / "hw08" / "verification.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"\n{passed}/{len(CHECKS)} checks passed -> {out.relative_to(ROOT)}")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
