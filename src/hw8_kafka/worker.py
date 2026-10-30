"""Part 1 worker: consumes s4098_entity_requests, replies on reply_to.

    python -m src.hw8_kafka.worker   (runs in the s4098-incident-worker container)

Offsets are committed manually, only after the response has been written to
Kafka, so a crash between 'process' and 'reply' leads to redelivery, not loss.
HW8_IDEMPOTENCY=off turns the correlation_id cache off (Part 3 'before' run).
"""

from __future__ import annotations

import asyncio
import json
import os
import signal

from aiokafka import AIOKafkaConsumer

from src.hw8_kafka.config import (
    DEAD_LETTER_TOPIC,
    KAFKA_BOOTSTRAP,
    PREFIX,
    REQUEST_TOPIC,
    RESPONSE_TOPIC,
    WORKER_GROUP,
    banner,
    log,
    now_iso,
)
from src.hw8_kafka.incidents import IncidentService
from src.hw8_kafka.topics import encode, ensure_topics, make_producer

C = "WORKER"
REQUIRED_KEYS = ("correlation_id", "reply_to", "operation", "data")


def short(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False)


async def main() -> None:
    banner("Part 1 worker (python -m src.hw8_kafka.worker)")
    idempotency = os.environ.get("HW8_IDEMPOTENCY", "on").lower() != "off"
    service = IncidentService(idempotency=idempotency)
    await ensure_topics(C)

    consumer = AIOKafkaConsumer(
        REQUEST_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=WORKER_GROUP,
        enable_auto_commit=False,  # commit only after the reply is written
        auto_offset_reset="earliest",
    )
    producer = await make_producer()
    await consumer.start()
    log(
        C,
        f"group={WORKER_GROUP} topic={REQUEST_TOPIC} "
        f"idempotency={'on' if idempotency else 'off'}",
    )
    log(C, "Consumer is ready and listening...")

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    try:
        while not stop.is_set():
            batch = await consumer.getmany(timeout_ms=500)
            for tp, messages in batch.items():
                for msg in messages:
                    await handle_message(consumer, producer, service, msg)
                    # commit exactly this message (not the whole fetched batch),
                    # and only after its reply has been written
                    await consumer.commit({tp: msg.offset + 1})
    finally:
        await consumer.stop()
        await producer.stop()
        log(C, "stopped")


async def handle_message(consumer, producer, service: IncidentService, msg) -> None:
    where = f"topic={msg.topic} partition={msg.partition} offset={msg.offset}"
    try:
        request = json.loads(msg.value.decode())
        if not isinstance(request, dict):
            raise ValueError("message is not a JSON object")
    except (UnicodeDecodeError, ValueError) as exc:
        log(C, f"RECEIVE {where} unreadable message ({exc}) -> {DEAD_LETTER_TOPIC}")
        await producer.send_and_wait(
            DEAD_LETTER_TOPIC,
            encode(
                {
                    "source_topic": msg.topic,
                    "source_partition": msg.partition,
                    "source_offset": msg.offset,
                    "error": str(exc),
                    "raw": msg.value.decode(errors="replace"),
                    "failed_at": now_iso(),
                    "failed_by": "incident-worker",
                }
            ),
        )
        return

    cid = request.get("correlation_id")
    log(C, f"RECEIVE {where} correlation_id={cid}")
    log(C, f"RECEIVE request={short(request)}")

    missing = [k for k in REQUIRED_KEYS if k not in request]
    reply_to = request.get("reply_to")
    if not (isinstance(reply_to, str) and reply_to.startswith(PREFIX + "_")):
        reply_to = RESPONSE_TOPIC  # never reply to a topic outside my prefix

    if missing:
        response = {
            "correlation_id": cid,
            "success": False,
            "error": "Invalid request: missing " + ", ".join(missing),
        }
        duplicate = False
    else:
        log(C, f"PROCESS operation={request['operation']} correlation_id={cid}")
        response, duplicate = service.handle(request)
        if duplicate:
            log(
                C,
                f"DUPLICATE correlation_id={cid} already processed -> returning the "
                "cached response, no new incident created (store "
                f"size={len(service.incidents)})",
            )
        else:
            log(
                C,
                f"PROCESS done success={response['success']} correlation_id={cid} "
                f"(store size={len(service.incidents)})",
            )

    meta = await producer.send_and_wait(
        reply_to, encode(response), key=(cid or "").encode()
    )
    log(
        C,
        f"REPLY sent to topic={meta.topic} partition={meta.partition} "
        f"offset={meta.offset} "
        f"correlation_id={cid}",
    )
    log(C, f"REPLY response={short(response)}")


if __name__ == "__main__":
    asyncio.run(main())
