"""Shared consume -> process -> produce loop for the Planner, Writer and Reviewer.

All Part 3 behavior lives here, so every agent gets it the same way:

* offset commit   - "after-success" (default): the offset of a message is
                    committed only after its output was written to Kafka.
                    "auto" (Part 3 before-run): Kafka auto-commit, which can
                    commit a message that is still being processed.
* idempotency     - correlation_ids that were already completed are skipped,
                    so a replayed message causes no second output.
* poison messages - "dlq" (default): bounded retries with backoff, then the
                    message goes to s4098_dead_letter and is committed, so it
                    no longer blocks the partition. "block" (before-run):
                    retry forever and never move on.
* experiments     - test messages carry "experiment": "<name>"; an agent only
                    handles messages whose tag equals its own --experiment, so
                    test runs never leak into the normal pipeline (or back).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
from dataclasses import dataclass
from typing import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, ConsumerRebalanceListener, TopicPartition

from src.hw8_kafka.config import (
    DEAD_LETTER_TOPIC,
    KAFKA_BOOTSTRAP,
    banner,
    log,
    now_iso,
)
from src.hw8_kafka.topics import encode, ensure_topics, make_producer


class PoisonMessage(ValueError):
    """The message content is invalid; retrying will not fix it."""


@dataclass
class AgentContext:
    name: str
    instance: str
    llm: str
    work_seconds: float


Handler = Callable[[dict, AgentContext], Awaitable[dict]]


def agent_args(name: str, default_group: str) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=f"HW8 {name} agent")
    p.add_argument("--instance", default=f"{name.lower()}-1")
    p.add_argument("--group", default=default_group)
    p.add_argument(
        "--commit", choices=["after-success", "auto"], default="after-success"
    )
    p.add_argument("--poison-policy", choices=["dlq", "block"], default="dlq")
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument(
        "--backoff", type=float, default=0.5, help="first retry delay, doubles"
    )
    p.add_argument("--no-idempotency", action="store_true")
    p.add_argument(
        "--experiment", default=None, help="only handle messages with this tag"
    )
    p.add_argument("--offset-reset", choices=["earliest", "latest"], default="earliest")
    p.add_argument("--event-log", default=None, help="append one JSON line per message")
    p.add_argument(
        "--llm", choices=["ollama", "stub"], default=os.environ.get("HW8_LLM", "ollama")
    )
    p.add_argument(
        "--work-seconds", type=float, default=0.0, help="stub: simulated work"
    )
    return p.parse_args()


class _Assignments(ConsumerRebalanceListener):
    """Logs every assignment and pins a start offset for brand-new groups.

    A new test group with offset-reset=latest has no committed offset. If it
    crashed before its first commit, a restart would jump to the end and skip
    the message. Committing the current position on first assignment makes
    'restart from the committed offset' well defined.
    """

    def __init__(self, consumer: AIOKafkaConsumer, tag: str):
        self.consumer = consumer
        self.tag = tag

    async def on_partitions_revoked(self, revoked):
        if revoked:
            log(
                self.tag,
                f"partitions revoked: {sorted(tp.partition for tp in revoked)}",
            )

    async def on_partitions_assigned(self, assigned):
        for tp in sorted(assigned, key=lambda t: t.partition):
            committed = await self.consumer.committed(tp)
            if committed is None:
                committed = await self.consumer.position(tp)
                await self.consumer.commit({tp: committed})
            log(
                self.tag,
                f"assigned {tp.topic}[{tp.partition}] start offset={committed}",
            )
        log(
            self.tag, f"ASSIGNMENT partitions={sorted(tp.partition for tp in assigned)}"
        )


class Agent:
    def __init__(
        self,
        *,
        name: str,
        in_topic: str,
        out_topic: str,
        handler: Handler,
        args: argparse.Namespace,
    ):
        self.name = name
        self.in_topic = in_topic
        self.out_topic = out_topic
        self.handler = handler
        self.args = args
        self.tag = f"{name}:{args.instance}"
        self.auto_commit = args.commit == "auto"
        self.completed: set[str] = set()  # idempotency: finished correlation_ids
        self.ctx = AgentContext(name, args.instance, args.llm, args.work_seconds)

    # ---------------------------------------------------------------- setup
    async def run(self) -> None:
        banner(
            f"{self.name} agent instance={self.args.instance} group={self.args.group}"
        )
        await ensure_topics(self.tag)
        self.consumer = AIOKafkaConsumer(
            bootstrap_servers=KAFKA_BOOTSTRAP,
            group_id=self.args.group,
            client_id=self.args.instance,
            enable_auto_commit=self.auto_commit,  # False unless the before-run
            auto_commit_interval_ms=500,
            auto_offset_reset=self.args.offset_reset,
            session_timeout_ms=6000,
            heartbeat_interval_ms=1000,
        )
        self.consumer.subscribe(
            [self.in_topic], listener=_Assignments(self.consumer, self.tag)
        )
        self.producer = await make_producer()
        await self.consumer.start()
        a = self.args
        log(
            self.tag,
            f"ready: {self.in_topic} -> {self.out_topic} | commit={a.commit} "
            f"poison-policy={a.poison_policy} max-attempts={a.max_attempts} "
            f"idempotency={'off' if a.no_idempotency else 'on'} llm={a.llm} "
            f"experiment={a.experiment}",
        )
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        try:
            while not stop.is_set():
                batch = await self.consumer.getmany(timeout_ms=500, max_records=1)
                for messages in batch.values():
                    for msg in messages:
                        await self.handle(msg)
        finally:
            await self.consumer.stop()
            await self.producer.stop()
            log(self.tag, "stopped")

    # -------------------------------------------------------------- helpers
    async def commit(self, msg) -> None:
        """Commit exactly this message's offset (+1). Called only when done."""
        if self.auto_commit:
            return  # before-run: the background auto-commit already did it
        tp = TopicPartition(msg.topic, msg.partition)
        await self.consumer.commit({tp: msg.offset + 1})
        log(self.tag, f"COMMIT partition={msg.partition} offset={msg.offset + 1}")

    def record(self, **event) -> None:
        if self.args.event_log:
            with open(self.args.event_log, "a") as fh:
                fh.write(json.dumps({"instance": self.args.instance, **event}) + "\n")

    @staticmethod
    def parse(msg) -> dict:
        try:
            value = json.loads(msg.value.decode())
        except (UnicodeDecodeError, ValueError) as exc:
            raise PoisonMessage(f"not valid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise PoisonMessage("message is not a JSON object")
        return value

    # ------------------------------------------------------------ main step
    async def handle(self, msg) -> None:
        where = f"partition={msg.partition} offset={msg.offset}"
        try:
            message = self.parse(msg)
        except PoisonMessage:
            message = None  # unreadable: let the retry policy deal with it
        if message is not None and message.get("experiment") != self.args.experiment:
            await self.commit(msg)  # not for this run: skip silently
            return

        cid = (message or {}).get("correlation_id")
        if (
            message is not None
            and not self.args.no_idempotency
            and cid in self.completed
        ):
            log(
                self.tag,
                f"DUPLICATE {where} correlation_id={cid} already done -> skipped, no "
                "output",
            )
            self.record(
                event="duplicate_skipped",
                correlation_id=cid,
                partition=msg.partition,
                offset=msg.offset,
                at=now_iso(),
            )
            await self.commit(msg)
            return

        log(self.tag, f"RECEIVE from {msg.topic} {where} correlation_id={cid}")
        attempt = 0
        while True:
            attempt += 1
            started = now_iso()
            try:
                if message is None:
                    self.parse(msg)  # raises again
                log(self.tag, f"PROCESS start correlation_id={cid} attempt={attempt}")
                output = await self.handler(message, self.ctx)
                break
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                log(
                    self.tag,
                    f"FAIL {where} correlation_id={cid} attempt={attempt} "
                    f"error={error}",
                )
                self.record(
                    event="failed_attempt",
                    correlation_id=cid,
                    partition=msg.partition,
                    offset=msg.offset,
                    attempt=attempt,
                    error=error,
                    at=now_iso(),
                )
                if self.args.poison_policy == "block":
                    # before-run: no limit, no dead-letter -> partition is stuck
                    await asyncio.sleep(self.args.backoff)
                    continue
                if attempt >= self.args.max_attempts:
                    await self.dead_letter(msg, message, error, attempt)
                    await self.commit(msg)
                    return
                delay = self.args.backoff * (2 ** (attempt - 1))
                log(
                    self.tag,
                    f"RETRY in {delay:.1f}s ({attempt}/{self.args.max_attempts})",
                )
                await asyncio.sleep(delay)

        # stamp the trace and forward; correlation_id is copied unchanged
        output["correlation_id"] = cid
        if message.get("experiment") is not None:
            output["experiment"] = message["experiment"]
        output["trace"] = list(message.get("trace", [])) + [
            {
                "agent": self.name,
                "instance": self.args.instance,
                "in_topic": msg.topic,
                "partition": msg.partition,
                "offset": msg.offset,
                "received_at": started,
                "sent_at": now_iso(),
            }
        ]
        key = str(message.get("partition_key") or cid or "").encode() or None
        meta = await self.producer.send_and_wait(
            self.out_topic, encode(output), key=key
        )
        log(
            self.tag,
            f"SEND to {meta.topic} partition={meta.partition} offset={meta.offset} "
            f"correlation_id={cid}",
        )
        self.record(
            event="processed",
            correlation_id=cid,
            partition=msg.partition,
            offset=msg.offset,
            entity_id=message.get("incident_id"),
            seq=message.get("seq"),
            started_at=started,
            finished_at=now_iso(),
            attempts=attempt,
        )
        if cid and not self.args.no_idempotency:
            self.completed.add(cid)
        await self.commit(msg)  # only now is the input offset committed

    async def dead_letter(self, msg, message, error: str, attempts: int) -> None:
        entry = {
            "correlation_id": (message or {}).get("correlation_id"),
            "experiment": (message or {}).get("experiment"),
            "source_topic": msg.topic,
            "source_partition": msg.partition,
            "source_offset": msg.offset,
            "failed_by": self.tag,
            "attempts": attempts,
            "error": error,
            "original": msg.value.decode(errors="replace"),
            "failed_at": now_iso(),
        }
        meta = await self.producer.send_and_wait(DEAD_LETTER_TOPIC, encode(entry))
        log(
            self.tag,
            f"DEAD-LETTER {DEAD_LETTER_TOPIC} partition={meta.partition} "
            f"offset={meta.offset} "
            f"after {attempts} attempts (source offset={msg.offset}) -> moving on",
        )
        self.record(
            event="dead_lettered",
            correlation_id=entry["correlation_id"],
            partition=msg.partition,
            offset=msg.offset,
            attempts=attempts,
            error=error,
            at=now_iso(),
        )
