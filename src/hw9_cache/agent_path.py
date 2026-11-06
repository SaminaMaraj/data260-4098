"""The HW8 agent path that runs on a cache miss.

inproc (default): calls the HW8 Planner -> Writer -> Reviewer handlers from
    src/hw8_kafka/agents.py one after another in this process. They are the
    same functions the Kafka agents run, and they call qwen3:8b through
    src/model_client.py (the adapter).
kafka: puts the question on s4098_inbox and waits for s4098_final, i.e. the
    full HW8 Kafka pipeline (needs Kafka and the three agent terminals).

--llm stub uses the HW8 stub mode (no Ollama), only for offline tests.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid

from src.hw8_kafka.agent_runtime import AgentContext
from src.hw8_kafka.agents import plan, review, write

GROUNDING_RULE = (
    "Use only the facts below for any names, codes or numbers. If the facts do "
    "not cover the question, say that the s4098_rel database has no record for it."
)


def grounded_question(question: str, facts_prompt: str) -> str:
    return (
        f"{question}\n\nFacts from the s4098_rel transit incident database "
        f"({GROUNDING_RULE}):\n{facts_prompt}"
    )


class AgentPath:
    def __init__(self, mode: str = "inproc", llm: str = "real", timeout: float = 600):
        self.mode = mode
        self.llm = llm
        self.timeout = timeout

    def run(self, question: str, facts_prompt: str) -> dict:
        full = grounded_question(question, facts_prompt)
        t0 = time.perf_counter()
        if self.mode == "kafka":
            result = asyncio.run(self._via_kafka(full))
        else:
            result = asyncio.run(self._inproc(full))
        result["agent_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        return result

    async def _inproc(self, full_question: str) -> dict:
        cid = str(uuid.uuid4())
        stages = {}
        msg = {"correlation_id": cid, "question": full_question}
        for name, handler in (
            ("PLANNER", plan),
            ("WRITER", write),
            ("REVIEWER", review),
        ):
            ctx = AgentContext(
                name=name,
                instance=f"{name.lower()}-hw9",
                llm=self.llm,
                work_seconds=0.0,
            )
            t = time.perf_counter()
            msg = await handler(msg, ctx)
            stages[name] = round((time.perf_counter() - t) * 1000, 2)
        return {
            "answer": msg["answer"],
            "status": msg.get("status"),
            "review": msg.get("review"),
            "stage_ms": stages,
            "path": "inproc (HW8 Planner->Writer->Reviewer via model_client)",
        }

    async def _via_kafka(self, full_question: str) -> dict:
        from src.hw8_kafka.config import FINAL_TOPIC, INBOX_TOPIC
        from src.hw8_kafka.topics import (
            encode,
            ensure_topics,
            make_producer,
            tail_consumer,
        )

        await ensure_topics("HW9")
        final = await tail_consumer(FINAL_TOPIC)
        producer = await make_producer()
        cid = str(uuid.uuid4())
        await producer.send_and_wait(
            INBOX_TOPIC,
            encode(
                {
                    "correlation_id": cid,
                    "question": full_question,
                    "sender": "hw9_semantic_cache",
                }
            ),
            key=cid.encode(),
        )
        await producer.stop()
        try:
            async with asyncio.timeout(self.timeout):
                async for m in final:
                    value = json.loads(m.value.decode())
                    if value.get("correlation_id") == cid:
                        return {
                            "answer": value["answer"],
                            "status": value.get("status"),
                            "review": value.get("review"),
                            "stage_ms": {},
                            "path": "kafka (s4098_inbox -> s4098_final)",
                        }
        finally:
            await final.stop()
        raise TimeoutError("no answer on s4098_final")
