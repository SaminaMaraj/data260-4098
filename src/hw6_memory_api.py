"""FastAPI endpoints for HW6 conversational memory."""

from __future__ import annotations

import time
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pymongo.errors import PyMongoError

from .hw6_memory import (
    build_prompt,
    maybe_create_summaries,
    record_message,
    save_episode_facts,
)
from .file_memory import handle_memory_command
from .model_client import complete
from .mongo_db import (
    get_episodes_collection,
    get_messages_collection,
    get_summaries_collection,
)


router = APIRouter(prefix="/api", tags=["HW6 Memory"])


class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100)
    session_id: str | None = Field(default=None, max_length=100)
    message: str = Field(..., min_length=1, max_length=4000)


class MemoryCommandRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=20)
    recent_messages: list[str] = Field(default_factory=list)


@router.post("/chat")
def chat(payload: ChatRequest) -> dict:
    started = time.perf_counter()
    try:
        record_message(payload.user_id, payload.session_id, "user", payload.message)
        prompt_messages, accounting = build_prompt(
            payload.user_id, payload.session_id, payload.message
        )
        model_result = complete(prompt_messages)
        reply = model_result.get("content", "").strip()
        if not reply:
            raise HTTPException(status_code=502, detail="The local model returned an empty reply.")
        record_message(payload.user_id, payload.session_id, "assistant", reply)
        save_episode_facts(payload.user_id, payload.session_id, payload.message)
        summaries_created = maybe_create_summaries(payload.user_id, payload.session_id)
        accounting.update(
            {
                "prompt_tokens": model_result.get("input_tokens", 0),
                "completion_tokens": model_result.get("output_tokens", 0),
                "total_tokens": model_result.get("total_tokens", 0),
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "model": model_result.get("model"),
            }
        )
        return {
            "reply": reply,
            "memory_used": accounting,
            "summaries_created": len(summaries_created),
        }
    except HTTPException:
        raise
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB error in chat: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Chat model error: {exc}") from exc


@router.post("/memory/command")
def memory_command(payload: MemoryCommandRequest) -> dict:
    return handle_memory_command(payload.command, payload.recent_messages)


def _iso(document: dict | None) -> dict | None:
    if document is None:
        return None
    result = dict(document)
    result.pop("_id", None)
    created_at = result.get("created_at")
    if isinstance(created_at, datetime):
        result["created_at"] = created_at.isoformat()
    return result


@router.get("/memory/{user_id}")
def get_memory(user_id: str) -> dict:
    try:
        messages = list(
            get_messages_collection()
            .find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(16)
        )
        messages.reverse()
        session_summary = get_summaries_collection().find_one(
            {"user_id": user_id, "scope": "session"}, sort=[("created_at", -1)]
        )
        lifetime_summary = get_summaries_collection().find_one(
            {"user_id": user_id, "scope": "user", "session_id": None},
            sort=[("created_at", -1)],
        )
        episodes = list(
            get_episodes_collection()
            .find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(20)
        )
        return {
            "messages": [_iso(item) for item in messages],
            "latest_session_summary": _iso(session_summary),
            "latest_lifetime_summary": _iso(lifetime_summary),
            "episodes": [_iso(item) for item in episodes],
        }
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB error while reading memory: {exc}") from exc


@router.get("/aggregate/{user_id}")
def get_aggregate(user_id: str) -> dict:
    try:
        daily_counts = list(
            get_messages_collection().aggregate(
                [
                    {"$match": {"user_id": user_id}},
                    {
                        "$group": {
                            "_id": {
                                "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
                            },
                            "count": {"$sum": 1},
                        }
                    },
                    {"$sort": {"_id": 1}},
                ]
            )
        )
        summaries = list(
            get_summaries_collection()
            .find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(5)
        )
        return {
            "daily_message_counts": [
                {"date": item["_id"], "count": item["count"]} for item in daily_counts
            ],
            "recent_summaries": [_iso(item) for item in summaries],
        }
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB error while aggregating memory: {exc}") from exc

