"""Part 1 FastAPI wrapper: HTTP in, Kafka request/response behind it.

    uvicorn src.hw8_kafka.api:app --host 0.0.0.0 --port 8498
    (runs in the s4098-incident-api container)

POST /incidents/kafka  {"correlation_id": "...", "operation": "...", "data": {...}}
The caller's correlation_id is kept unchanged; one is created only if the
caller did not send one.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.hw8_kafka.config import (
    PORT_BASE,
    REQUEST_TOPIC,
    RESPONSE_TOPIC,
    STUDENT_NAME,
    banner,
    log,
)
from src.hw8_kafka.topics import encode, ensure_topics, make_producer, tail_consumer

C = "API"
TIMEOUT_SECONDS = 15


class KafkaRPC:
    def __init__(self):
        self.producer = None
        self.consumer = None
        self.pending: dict[str, asyncio.Future] = {}
        self.task = None

    async def start(self):
        await ensure_topics(C)
        self.producer = await make_producer()
        self.consumer = await tail_consumer(RESPONSE_TOPIC)
        self.task = asyncio.create_task(self._listen())
        log(
            C,
            f"KafkaRPC ready: requests -> {REQUEST_TOPIC}, replies <- {RESPONSE_TOPIC}",
        )

    async def stop(self):
        if self.task:
            self.task.cancel()
        await self.consumer.stop()
        await self.producer.stop()

    async def _listen(self):
        async for msg in self.consumer:
            try:
                response = json.loads(msg.value.decode())
            except ValueError:
                continue
            cid = response.get("correlation_id")
            future = self.pending.pop(cid, None)
            if future is None:
                log(
                    C,
                    f"RESPONSE offset={msg.offset} correlation_id={cid} (no waiting "
                    "caller)",
                )
                continue
            log(
                C,
                f"RESPONSE received from topic={msg.topic} partition={msg.partition} "
                f"offset={msg.offset} correlation_id={cid} (matched)",
            )
            if not future.done():
                future.set_result(response)

    async def request(self, operation: str, data: Any, correlation_id: str) -> dict:
        message = {
            "correlation_id": correlation_id,
            "reply_to": RESPONSE_TOPIC,
            "operation": operation,
            "data": data,
        }
        future = asyncio.get_running_loop().create_future()
        self.pending[correlation_id] = future
        meta = await self.producer.send_and_wait(
            REQUEST_TOPIC, encode(message), key=correlation_id.encode()
        )
        log(
            C,
            f"SEND to topic={meta.topic} partition={meta.partition} "
            f"offset={meta.offset} "
            f"correlation_id={correlation_id}",
        )
        log(C, f"SEND request={json.dumps(message)}")
        try:
            response = await asyncio.wait_for(future, timeout=TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            self.pending.pop(correlation_id, None)
            log(C, f"TIMEOUT correlation_id={correlation_id}")
            return {
                "correlation_id": correlation_id,
                "success": False,
                "error": f"No response from worker within {TIMEOUT_SECONDS}s",
            }
        log(C, f"RETURN HTTP response to caller correlation_id={correlation_id}")
        return response


rpc = KafkaRPC()


@asynccontextmanager
async def lifespan(app: FastAPI):
    banner("Part 1 FastAPI wrapper")
    await rpc.start()
    log(C, f"FastAPI server started at http://127.0.0.1:{PORT_BASE}")
    yield
    await rpc.stop()


app = FastAPI(title=f"HW8 incident Kafka API - {STUDENT_NAME}", lifespan=lifespan)


class IncidentRequest(BaseModel):
    operation: str
    data: Any = Field(default_factory=dict)
    correlation_id: str | None = None


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "hw8-incident-api", "port": PORT_BASE}


@app.post("/incidents/kafka")
async def incident_operation(body: IncidentRequest) -> dict:
    correlation_id = body.correlation_id or str(uuid.uuid4())
    log(
        C,
        f"HTTP POST /incidents/kafka operation={body.operation} "
        f"correlation_id={correlation_id}",
    )
    return await rpc.request(body.operation, body.data, correlation_id)
