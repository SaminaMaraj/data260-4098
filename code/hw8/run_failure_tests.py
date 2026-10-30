"""HW8 Part 3: failure behavior, each scenario before and after the fix.

Run from the repo root with the HW8 docker stack up (Kafka on localhost:9092).
Stop your Part 2 agents first (Ctrl+C) - the tests start their own Writers.

    python code/hw8/run_failure_tests.py duplicate       --mode before|after
    python code/hw8/run_failure_tests.py duplicate-agent --mode before|after
    python code/hw8/run_failure_tests.py consumer-death --mode before|after [--real-llm]
    python code/hw8/run_failure_tests.py poison          --mode before|after
    python code/hw8/run_failure_tests.py ordering        --mode before|after
    python code/hw8/run_failure_tests.py summary         (writes METRICS.md tables)

'duplicate' replays a CREATE_INCIDENT to the Part 1 worker container. For
--mode before, recreate the worker with idempotency off first:
    HW8_IDEMPOTENCY=off docker compose -f docker-compose.hw8.yml up -d worker
and for --mode after with it on again (HW8_IDEMPOTENCY=on or unset).

Every run prints the agents' log lines inline, appends the console output to
reports/hw08/RUN_LOG.txt and writes its raw data to reports/hw08/raw/.
Test messages carry an "experiment" tag and every run uses its own consumer
group, so runs never see each other's messages.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import random
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from aiokafka.admin import AIOKafkaAdminClient  # noqa: E402

from src.hw8_kafka.config import (  # noqa: E402
    DEAD_LETTER_TOPIC,
    DRAFTS_TOPIC,
    KAFKA_BOOTSTRAP,
    PREFIX,
    REQUEST_TOPIC,
    RESPONSE_TOPIC,
    STUDENT_NAME,
    TASKS_TOPIC,
    VERIFY_SEED,
    now_iso,
)
from src.hw8_kafka.topics import (  # noqa: E402
    encode,
    ensure_topics,
    make_producer,
    tail_consumer,
)

HW8 = ROOT / "code" / "hw8"
REPORT = ROOT / "reports" / "hw08"
RAW = REPORT / "raw"
LOGS = RAW / "logs"
RESULTS = RAW / "failure_results.json"
RUN_LOG = REPORT / "RUN_LOG.txt"
CONSOLE: list[str] = []


def out(line: str = "") -> None:
    print(line, flush=True)
    CONSOLE.append(line)


def say(message: str) -> None:
    out(f"{now_iso()} [TEST] {message}")


# --------------------------------------------------------------- processes
class Proc:
    """An agent subprocess whose output is echoed inline and kept."""

    def __init__(self, label: str):
        self.label = label
        self.lines: list[str] = []
        self.proc = None

    async def start(self, *cmd: str) -> "Proc":
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-u",
            *cmd,
            cwd=ROOT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        self.reader = asyncio.create_task(self._read())
        return self

    async def _read(self):
        async for raw in self.proc.stdout:
            line = raw.decode(errors="replace").rstrip()
            self.lines.append(line)
            out(f"    | {line}")

    async def wait_for(self, pattern: str, timeout: float, start: int = 0) -> int:
        """Index of the first line (from `start`) containing pattern."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for i in range(start, len(self.lines)):
                if pattern in self.lines[i]:
                    return i
            if self.proc.returncode is not None:
                break
            await asyncio.sleep(0.1)
        raise TimeoutError(f"{self.label}: '{pattern}' not seen within {timeout}s")

    def count(self, pattern: str) -> int:
        return sum(pattern in line for line in self.lines)

    async def kill(self, sig=signal.SIGKILL):
        if self.proc and self.proc.returncode is None:
            self.proc.send_signal(sig)
            try:
                await asyncio.wait_for(self.proc.wait(), 10)
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()
        await asyncio.sleep(0.2)


def writer_cmd(instance: str, group: str, experiment: str, *extra: str) -> list[str]:
    return [
        str(HW8 / "writer.py"),
        "--instance",
        instance,
        "--group",
        group,
        "--experiment",
        experiment,
        "--offset-reset",
        "latest",
        *extra,
    ]


async def start_writer(label: str, *cmd: str) -> Proc:
    proc = await Proc(label).start(*cmd)
    await proc.wait_for("ASSIGNMENT partitions=", 60)
    return proc


async def committed_offsets(group: str, topic: str) -> dict[int, int]:
    admin = AIOKafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP)
    await admin.start()
    try:
        offsets = await admin.list_consumer_group_offsets(group)
        return {
            tp.partition: meta.offset
            for tp, meta in offsets.items()
            if tp.topic == topic
        }
    finally:
        await admin.close()


async def collect(consumer, match, seconds: float) -> list[dict]:
    """Messages from a tail consumer for which match(value) is true."""
    found = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        batch = await consumer.getmany(timeout_ms=200)
        for messages in batch.values():
            for msg in messages:
                try:
                    value = json.loads(msg.value.decode())
                except ValueError:
                    continue
                if match(value):
                    found.append(
                        {"partition": msg.partition, "offset": msg.offset, **value}
                    )
    return found


def task_message(cid: str, experiment: str, **extra) -> dict:
    return {
        "correlation_id": cid,
        "experiment": experiment,
        "question": "Test task: what should riders be told during a 20-minute delay?",
        "plan": {
            "steps": ["State the delay", "Give the alternative route"],
            "focus": "test",
        },
        **extra,
    }


def worker_lines(needle: str, since: str) -> list[str]:
    """Worker container log lines containing needle (HW8_WORKER_LOG = file instead)."""
    if os.environ.get("HW8_WORKER_LOG"):
        text = Path(os.environ["HW8_WORKER_LOG"]).read_text()
    else:
        try:
            done = subprocess.run(
                ["docker", "logs", "--since", since, "s4098-incident-worker"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            text = done.stdout + done.stderr
        except (OSError, subprocess.SubprocessError):
            return ["(worker logs not available)"]
    return [ln for ln in text.splitlines() if needle in ln]


# ---------------------------------------------------- 1. duplicate delivery
async def test_duplicate(mode: str, run_id: str) -> dict:
    """Replay one CREATE_INCIDENT (same correlation_id) to the Part 1 worker."""
    say(f"duplicate delivery, mode={mode}: replay CREATE_INCIDENT to the worker")
    started = now_iso()
    SHOWN_FIELDS = ("success", "incident_id", "message", "error")
    responses = await tail_consumer(RESPONSE_TOPIC)
    producer = await make_producer()
    cid = str(uuid.uuid4())
    request = {
        "correlation_id": cid,
        "reply_to": RESPONSE_TOPIC,
        "operation": "CREATE_INCIDENT",
        "data": {
            "incidentTitle": "Duplicate delivery test",
            "routeLine": "VTA Route 66",
            "submitterEmail": "kazisaminamaraj.mumu@sjsu.edu",
            "description": "Replayed CREATE_INCIDENT used to test idempotency in HW8.",
            "category": "delay",
            "termsAccepted": True,
        },
    }
    raw = encode(request)
    results = []
    for attempt in ("original", "replay"):
        meta = await producer.send_and_wait(REQUEST_TOPIC, raw, key=cid.encode())
        say(
            f"SEND {attempt} to {meta.topic} offset={meta.offset} correlation_id={cid} "
            "(identical bytes)"
        )
        got = await collect(responses, lambda v: v.get("correlation_id") == cid, 6)
        for r in got:
            say(
                f"RESPONSE to {attempt}: "
                + json.dumps({k: r.get(k) for k in SHOWN_FIELDS})
            )
        results += got

    ids = sorted({r.get("incident_id") for r in results if r.get("incident_id")})
    existing = []
    for incident_id in ids:  # how many incidents really exist for this cid?
        get_cid = str(uuid.uuid4())
        await producer.send_and_wait(
            REQUEST_TOPIC,
            encode(
                {
                    "correlation_id": get_cid,
                    "reply_to": RESPONSE_TOPIC,
                    "operation": "GET_INCIDENT",
                    "data": {"incident_id": incident_id},
                }
            ),
        )
        got = await collect(
            responses, lambda v, g=get_cid: v.get("correlation_id") == g, 4
        )
        if got and got[0].get("success"):
            existing.append(incident_id)
    await producer.stop()
    await responses.stop()

    say("worker log lines for this correlation_id:")
    for line in worker_lines(cid, started):
        out(f"    | {line}")
    verdict = (
        f"{len(existing)} incident(s) created by 2 deliveries of one correlation_id"
        + (" -> extra side effect" if len(existing) > 1 else " -> no extra side effect")
    )
    say(verdict)
    if mode == "after" and len(existing) > 1:
        say("WARNING: the worker still creates duplicates - is HW8_IDEMPOTENCY on?")
    return {
        "correlation_id": cid,
        "responses": len(results),
        "incident_ids_returned": ids,
        "incidents_existing": existing,
        "extra_side_effect": len(existing) > 1,
        "summary": verdict,
    }


async def test_duplicate_agent(mode: str, run_id: str) -> dict:
    """Replay one task to the Writer; count drafts produced for it."""
    exp, group = f"dup-agent-{mode}-{run_id}", f"{PREFIX}_writers_dup_{mode}_{run_id}"
    say(f"duplicate delivery to the Writer, mode={mode}")
    extra = ["--llm", "stub", "--work-seconds", "0.3"]
    if mode == "before":
        extra.append("--no-idempotency")
    writer = await start_writer("writer", *writer_cmd("writer-dup", group, exp, *extra))
    drafts = await tail_consumer(DRAFTS_TOPIC)
    producer = await make_producer()
    cid = str(uuid.uuid4())
    raw = encode(task_message(cid, exp))
    for attempt in ("original", "replay"):
        meta = await producer.send_and_wait(TASKS_TOPIC, raw, key=cid.encode())
        say(
            f"SEND {attempt} task to {meta.topic}[{meta.partition}] "
            f"offset={meta.offset} correlation_id={cid}"
        )
    found = await collect(drafts, lambda v: v.get("correlation_id") == cid, 5)
    await producer.stop()
    await drafts.stop()
    await writer.kill(signal.SIGTERM)
    verdict = f"{len(found)} draft(s) produced for 2 deliveries of one correlation_id"
    say(verdict)
    return {
        "correlation_id": cid,
        "drafts_produced": len(found),
        "duplicate_skipped_logged": writer.count("DUPLICATE") > 0,
        "extra_side_effect": len(found) > 1,
        "summary": verdict,
    }


# ------------------------------------------------------- 2. consumer death
async def test_consumer_death(mode: str, run_id: str, real_llm: bool) -> dict:
    exp, group = f"death-{mode}-{run_id}", f"{PREFIX}_writers_death_{mode}_{run_id}"
    commit = "auto" if mode == "before" else "after-success"
    llm = ["--llm", "ollama"] if real_llm else ["--llm", "stub", "--work-seconds", "6"]
    say(
        f"consumer death, mode={mode}: Writer commit={commit}, killed with SIGKILL "
        "mid-processing"
    )
    writer = await start_writer(
        "writer", *writer_cmd("writer-1", group, exp, "--commit", commit, *llm)
    )
    drafts = await tail_consumer(DRAFTS_TOPIC)
    producer = await make_producer()
    cid = str(uuid.uuid4())
    meta = await producer.send_and_wait(
        TASKS_TOPIC, encode(task_message(cid, exp)), key=cid.encode()
    )
    say(
        f"SEND task to {meta.topic}[{meta.partition}] offset={meta.offset} "
        f"correlation_id={cid}"
    )
    await writer.wait_for("PROCESS start", 30)
    await asyncio.sleep(2.5)  # well inside the work time; auto-commit interval is 0.5 s
    say(
        f"KILL -9 Writer pid={writer.proc.pid} while it is processing "
        f"offset={meta.offset}"
    )
    await writer.kill(signal.SIGKILL)
    committed = await committed_offsets(group, TASKS_TOPIC)
    c = committed.get(meta.partition)
    if c is not None and c > meta.offset:
        meaning = "already committed -> will NOT be redelivered"
    else:
        meaning = "not committed -> will be redelivered"
    say(
        f"committed offset for {TASKS_TOPIC}[{meta.partition}] after the kill = {c} "
        f"(message offset {meta.offset}; {meaning})"
    )

    say("RESTART Writer (same consumer group)")
    restarted = await start_writer(
        "writer",
        *writer_cmd("writer-1-restarted", group, exp, "--commit", commit, *llm),
    )
    wait = 90 if real_llm else 25
    found = await collect(drafts, lambda v: v.get("correlation_id") == cid, wait)
    redelivered = restarted.count(f"offset={meta.offset} correlation_id={cid}") > 0
    committed_after = await committed_offsets(group, TASKS_TOPIC)
    await restarted.kill(signal.SIGTERM)
    await producer.stop()
    await drafts.stop()
    verdict = (
        f"redelivered after restart: {redelivered}; drafts produced: {len(found)}; "
        f"committed offset after kill={c}, at the "
        f"end={committed_after.get(meta.partition)}"
    )
    say(verdict)
    return {
        "correlation_id": cid,
        "message_offset": meta.offset,
        "partition": meta.partition,
        "commit_mode": commit,
        "committed_after_kill": c,
        "committed_at_end": committed_after.get(meta.partition),
        "redelivered": redelivered,
        "drafts_produced": len(found),
        "message_lost": len(found) == 0,
        "summary": verdict,
    }


# --------------------------------------------------------- 3. poison message
async def test_poison(mode: str, run_id: str) -> dict:
    exp, group = f"poison-{mode}-{run_id}", f"{PREFIX}_writers_poison_{mode}_{run_id}"
    policy = "block" if mode == "before" else "dlq"
    say(f"poison message, mode={mode}: Writer poison-policy={policy}")
    writer = await start_writer(
        "writer",
        *writer_cmd(
            "writer-1",
            group,
            exp,
            "--poison-policy",
            policy,
            "--max-attempts",
            "3",
            "--backoff",
            "1.0" if mode == "before" else "0.5",
            "--llm",
            "stub",
            "--work-seconds",
            "0.2",
        ),
    )
    drafts = await tail_consumer(DRAFTS_TOPIC)
    dead = await tail_consumer(DEAD_LETTER_TOPIC)
    producer = await make_producer()
    key = f"poison-{run_id}".encode()  # same key -> same partition as the good message
    bad_cid, good_cid = str(uuid.uuid4()), str(uuid.uuid4())
    poison = {
        "correlation_id": bad_cid,
        "experiment": exp,
        "question": "?",
        "plan": "<<corrupted plan>>",
    }
    m1 = await producer.send_and_wait(TASKS_TOPIC, encode(poison), key=key)
    say(
        f"SEND poison task to {m1.topic}[{m1.partition}] offset={m1.offset} "
        f"correlation_id={bad_cid} plan={poison['plan']!r}"
    )
    m2 = await producer.send_and_wait(
        TASKS_TOPIC, encode(task_message(good_cid, exp)), key=key
    )
    say(
        f"SEND good task to {m2.topic}[{m2.partition}] offset={m2.offset} "
        f"correlation_id={good_cid}"
    )

    window = 15
    good = await collect(drafts, lambda v: v.get("correlation_id") == good_cid, window)
    dlq = await collect(dead, lambda v: v.get("correlation_id") == bad_cid, 1)
    attempts = writer.count("FAIL ")
    await writer.kill(signal.SIGTERM)
    await producer.stop()
    await drafts.stop()
    await dead.stop()
    verdict = (
        f"poison attempts in {window}s window: {attempts}; dead-lettered: {bool(dlq)}; "
        f"later good message processed: {bool(good)}"
    )
    say(verdict)
    return {
        "poison_correlation_id": bad_cid,
        "good_correlation_id": good_cid,
        "partition": m1.partition,
        "poison_offset": m1.offset,
        "good_offset": m2.offset,
        "policy": policy,
        "poison_attempts": attempts,
        "dead_lettered": bool(dlq),
        "dead_letter_entry": dlq[0] if dlq else None,
        "good_message_processed": bool(good),
        "summary": verdict,
    }


# --------------------------------------------------------------- 4. ordering
def ordering_messages() -> list[dict]:
    """20 related messages: 4 incidents x 5 status updates, seeded by VERIFY_SEED.

    Per incident the updates are created in order (seq 1..5); the 4 streams
    are interleaved at random, and each message gets a random work time.
    """
    rng = random.Random(VERIFY_SEED)
    incidents = [f"INC-{rng.randint(100000, 999999)}" for _ in range(4)]
    statuses = [
        "reported",
        "crew_dispatched",
        "crew_on_scene",
        "service_restored",
        "closed",
    ]
    next_seq = {i: 1 for i in incidents}
    messages = []
    while len(messages) < 20:
        incident = rng.choice([i for i in incidents if next_seq[i] <= 5])
        seq = next_seq[incident]
        next_seq[incident] += 1
        messages.append(
            {
                "incident_id": incident,
                "seq": seq,
                "status": statuses[seq - 1],
                "work_ms": rng.randint(50, 700),
                "plan": {
                    "steps": [
                        f"Update rider notice: {incident} is {statuses[seq - 1]}"
                    ],
                    "focus": "status update",
                },
            }
        )
    return messages


async def test_ordering(mode: str, run_id: str) -> dict:
    keyed = mode == "after"
    exp, group = f"order-{mode}-{run_id}", f"{PREFIX}_writers_order_{mode}_{run_id}"
    say(
        f"ordering, mode={mode}: 20 messages (VERIFY_SEED={VERIFY_SEED}) -> "
        f"{TASKS_TOPIC} "
        f"(2 partitions), 2 Writers in group {group}, "
        f"key={'incident_id' if keyed else 'none'}"
    )
    events = RAW / f"ordering_{mode}_events.jsonl"
    events.unlink(missing_ok=True)
    w = []
    for n in (1, 2):
        cmd = writer_cmd(
            f"writer-{n}", group, exp, "--llm", "stub", "--event-log", str(events)
        )
        w.append(await Proc(f"writer-{n}").start(*cmd))
    # wait until the group has settled: both Writers own exactly one partition
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        last = []
        for proc in w:
            lines = [ln for ln in proc.lines if "ASSIGNMENT partitions=" in ln]
            last.append(lines[-1].split("partitions=")[1] if lines else None)
        if all(a in ("[0]", "[1]") for a in last) and last[0] != last[1]:
            break
        await asyncio.sleep(0.2)
    else:
        raise TimeoutError("the two Writers did not split the two partitions")
    say(f"group settled: writer-1 owns {last[0]}, writer-2 owns {last[1]}")
    await asyncio.sleep(1)

    random.seed(VERIFY_SEED)  # aiokafka picks a random partition for key=None
    producer = await make_producer()
    sent = []
    for i, m in enumerate(ordering_messages(), 1):
        cid = str(uuid.uuid4())
        value = {"correlation_id": cid, "experiment": exp, "question": "", **m}
        if keyed:
            value["partition_key"] = m["incident_id"]
        key = m["incident_id"].encode() if keyed else None
        meta = await producer.send_and_wait(TASKS_TOPIC, encode(value), key=key)
        sent.append(
            {
                "send_index": i,
                "correlation_id": cid,
                "incident_id": m["incident_id"],
                "seq": m["seq"],
                "status": m["status"],
                "work_ms": m["work_ms"],
                "key": m["incident_id"] if keyed else "",
                "partition": meta.partition,
                "offset": meta.offset,
            }
        )
        say(
            f"SEND #{i:02d} {m['incident_id']} seq={m['seq']} "
            f"key={'incident_id' if keyed else 'none'} "
            f"-> partition={meta.partition} offset={meta.offset}"
        )
    await producer.stop()

    deadline = time.monotonic() + 60
    processed = []
    while time.monotonic() < deadline:
        if events.exists():
            processed = [
                json.loads(x) for x in events.read_text().splitlines() if x.strip()
            ]
            processed = [e for e in processed if e["event"] == "processed"]
        if len(processed) >= 20:
            break
        await asyncio.sleep(0.3)
    for proc in w:
        await proc.kill(signal.SIGTERM)

    by_cid = {e["correlation_id"]: e for e in processed}
    rows = []
    for s in sent:
        e = by_cid.get(s["correlation_id"], {})
        rows.append(
            {
                **s,
                "writer": e.get("instance"),
                "started_at": e.get("started_at"),
                "finished_at": e.get("finished_at"),
            }
        )
    done = sorted([r for r in rows if r["finished_at"]], key=lambda r: r["finished_at"])
    for rank, r in enumerate(done, 1):
        r["processed_rank"] = rank

    out()
    say("processing order (by finish time):")
    violations = {}
    partitions = {}
    for incident in sorted({r["incident_id"] for r in rows}):
        seqs = [r["seq"] for r in done if r["incident_id"] == incident]
        bad = sum(1 for a, b in zip(seqs, seqs[1:]) if b < a)
        violations[incident] = bad
        partitions[incident] = sorted(
            {r["partition"] for r in rows if r["incident_id"] == incident}
        )
        say(
            f"  {incident}: processed seq order {seqs} "
            f"partitions={partitions[incident]} "
            f"-> {'IN ORDER' if bad == 0 else f'OUT OF ORDER ({bad} inversions)'}"
        )
    for r in done:
        say(
            f"  #{r['processed_rank']:02d} {r['writer']} p{r['partition']} "
            f"o{r['offset']} "
            f"{r['incident_id']} seq={r['seq']} ({r['status']}) "
            f"finished={r['finished_at']}"
        )

    csv_path = RAW / f"ordering_{mode}_{'keyed' if keyed else 'nokey'}.csv"
    with csv_path.open("w", newline="") as fh:
        fields = [
            "send_index",
            "processed_rank",
            "incident_id",
            "seq",
            "status",
            "key",
            "partition",
            "offset",
            "writer",
            "work_ms",
            "started_at",
            "finished_at",
            "correlation_id",
        ]
        writer_csv = csv.DictWriter(fh, fieldnames=fields)
        writer_csv.writeheader()
        for r in sorted(rows, key=lambda r: r["send_index"]):
            writer_csv.writerow({k: r.get(k) for k in fields})
    total = sum(violations.values())
    split = sum(1 for p in partitions.values() if len(p) > 1)
    verdict = (
        f"{len(done)}/20 processed; {split}/4 incidents spread over both partitions; "
        f"{total} ordering inversions"
    )
    say(verdict + f"; saved {csv_path.relative_to(ROOT)}")
    return {
        "verify_seed": VERIFY_SEED,
        "keyed": keyed,
        "processed": len(done),
        "incidents_split_across_partitions": split,
        "inversions_total": total,
        "inversions_per_incident": violations,
        "partitions_per_incident": partitions,
        "csv": str(csv_path.relative_to(ROOT)),
        "summary": verdict,
    }


# ------------------------------------------------------------------ summary
ROWS = [
    ("duplicate", "Duplicate delivery (Part 1 worker, CREATE_INCIDENT replay)"),
    ("duplicate-agent", "Duplicate delivery (Writer, task replay)"),
    ("consumer-death", "Consumer killed mid-work"),
    ("poison", "Poison message"),
    ("ordering", "Two partitions/two consumers"),
]


def write_summary() -> None:
    results = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    lines = ["| Failure scenario | Before fix | After fix |", "|---|---|---|"]
    for key, label in ROWS:
        cell = []
        for mode in ("before", "after"):
            r = results.get(key, {}).get(mode)
            cell.append(f"{r['summary']} (run {r['run_id']})" if r else "not run")
        lines.append(f"| {label} | {cell[0]} | {cell[1]} |")
    table = "\n".join(lines)
    print(table)
    (RAW / "failure_table.md").write_text(table + "\n")
    print(f"\nsaved {RAW / 'failure_table.md'}")


# --------------------------------------------------------------------- main
async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("test", choices=[k for k, _ in ROWS] + ["summary"])
    p.add_argument("--mode", choices=["before", "after"])
    p.add_argument(
        "--real-llm", action="store_true", help="consumer-death with qwen3:8b"
    )
    a = p.parse_args()
    if a.test == "summary":
        write_summary()
        return 0
    if not a.mode:
        p.error("--mode before|after is required")

    RAW.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%H%M%S")
    out(
        f"{STUDENT_NAME} | run_failure_tests.py {a.test} --mode {a.mode} | run "
        f"{run_id} | "
        f"PREFIX={PREFIX} VERIFY_SEED={VERIFY_SEED} | {now_iso()}"
    )
    await ensure_topics("TEST")
    if a.test == "duplicate":
        result = await test_duplicate(a.mode, run_id)
    elif a.test == "duplicate-agent":
        result = await test_duplicate_agent(a.mode, run_id)
    elif a.test == "consumer-death":
        result = await test_consumer_death(a.mode, run_id, a.real_llm)
    elif a.test == "poison":
        result = await test_poison(a.mode, run_id)
    else:
        result = await test_ordering(a.mode, run_id)
    result.update({"run_id": run_id, "finished_at": now_iso()})

    results = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    results.setdefault(a.test, {})[a.mode] = result
    RESULTS.write_text(json.dumps(results, indent=2))
    (RAW / f"{a.test}_{a.mode}.json").write_text(json.dumps(result, indent=2))
    log_text = "\n".join(CONSOLE) + "\n"
    (LOGS / f"{a.test}_{a.mode}.log").write_text(log_text)
    with RUN_LOG.open("a") as fh:
        fh.write(
            f"\n===== Part 3 {a.test} --mode {a.mode} (run {run_id}) =====\n{log_text}"
        )
    out(
        f"saved raw/{a.test}_{a.mode}.json, raw/logs/{a.test}_{a.mode}.log, appended "
        "RUN_LOG.txt"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
