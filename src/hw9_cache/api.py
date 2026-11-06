"""HW9: cached Q&A endpoint (the ingress in front of the HW8 agent path).

    uvicorn src.hw9_cache.api:app --port 8499
    curl -s -X POST localhost:8499/qa -H 'Content-Type: application/json' \
         -d '{"question": "Who operates VTA Route 522?"}'
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from src.hw9_cache.config import DEFAULT_THRESHOLD
from src.hw9_cache.qa import build_qa

app = FastAPI(title="s4098 cached transit Q&A (HW9)")
_qa = None


def qa():
    global _qa
    if _qa is None:
        _qa = build_qa(
            float(os.environ.get("HW9_THRESHOLD", DEFAULT_THRESHOLD)),
            agent_mode=os.environ.get("HW9_AGENT_PATH", "inproc"),
        )
    return _qa


class Question(BaseModel):
    question: str


@app.post("/qa")
async def ask(body: Question) -> dict:
    res = await run_in_threadpool(qa().ask, body.question)
    return {
        k: res.get(k)
        for k in (
            "answer",
            "is_cached",
            "similarity",
            "latency_ms",
            "matched_query",
            "data_version",
            "invalidated",
            "timings",
        )
    }


@app.get("/qa/cache")
async def cache_info() -> dict:
    return {"entries": qa().cache.backend.size(), "threshold": qa().cache.threshold}
