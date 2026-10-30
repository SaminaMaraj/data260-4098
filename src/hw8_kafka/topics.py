"""Create the HW8 topics if they are missing (idempotent).

The broker runs with auto topic creation turned off, so a typo in a topic name
fails loudly instead of silently creating a new 1-partition topic.
"""

from __future__ import annotations

import asyncio
import json

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient, NewPartitions, NewTopic
from aiokafka.errors import KafkaConnectionError, TopicAlreadyExistsError

from src.hw8_kafka.config import KAFKA_BOOTSTRAP, TOPICS, log


async def wait_for_kafka(component: str, attempts: int = 30, delay: float = 2.0):
    """Return a started admin client once the broker answers."""
    last_error = None
    for attempt in range(1, attempts + 1):
        admin = AIOKafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP)
        try:
            await admin.start()
            await admin.list_topics()
            return admin
        except (KafkaConnectionError, OSError, Exception) as exc:  # noqa: BLE001
            last_error = exc
            try:
                await admin.close()
            except Exception:  # noqa: BLE001
                pass
            log(component, f"Kafka not ready (attempt {attempt}/{attempts}): {exc}")
            await asyncio.sleep(delay)
    raise RuntimeError(f"Kafka at {KAFKA_BOOTSTRAP} not reachable: {last_error}")


async def partition_counts(admin: AIOKafkaAdminClient, names) -> dict[str, int]:
    described = await admin.describe_topics(list(names))
    return {
        item["topic"]: len(item["partitions"])
        for item in described
        if item.get("error_code", 0) == 0
    }


async def ensure_topics(component: str = "TOPICS") -> dict[str, int]:
    admin = await wait_for_kafka(component)
    try:
        existing = set(await admin.list_topics())
        missing = [
            NewTopic(name, partitions, 1)
            for name, partitions in TOPICS.items()
            if name not in existing
        ]
        if missing:
            try:
                await admin.create_topics(missing)
            except TopicAlreadyExistsError:
                pass  # another process created it at the same moment
            log(component, "created topics: " + ", ".join(t.name for t in missing))
        await asyncio.sleep(0.5)
        counts = await partition_counts(admin, TOPICS)
        for name, wanted in TOPICS.items():
            if counts.get(name, 0) < wanted:
                await admin.create_partitions({name: NewPartitions(wanted)})
                log(component, f"increased {name} to {wanted} partitions")
        return await partition_counts(admin, TOPICS)
    finally:
        await admin.close()


def encode(value: dict) -> bytes:
    return json.dumps(value).encode()


async def make_producer() -> AIOKafkaProducer:
    # acks=all + idempotent producer: a broker retry cannot write a message twice
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        acks="all",
        enable_idempotence=True,
    )
    await producer.start()
    return producer


async def tail_consumer(topic: str) -> AIOKafkaConsumer:
    """Group-less consumer that reads only messages produced from now on.

    It is assigned all partitions directly (no group join, no rebalance wait),
    so a reply cannot be missed between 'send request' and 'start listening'.
    """
    consumer = AIOKafkaConsumer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=None,
        enable_auto_commit=False,
    )
    await consumer.start()
    partitions = consumer.partitions_for_topic(topic)
    if not partitions:
        await consumer._client.force_metadata_update()  # noqa: SLF001
        partitions = consumer.partitions_for_topic(topic) or {0}
    tps = [TopicPartition(topic, p) for p in sorted(partitions)]
    consumer.assign(tps)
    await consumer.seek_to_end(*tps)
    for tp in tps:  # resolve the end position now, before anything is sent
        await consumer.position(tp)
    return consumer


if __name__ == "__main__":
    print(asyncio.run(ensure_topics()))
