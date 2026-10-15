"""Short-, long-, and episodic-memory helpers for HW6."""

from __future__ import annotations

import math
import os
import re
import hashlib
from datetime import datetime, timezone
from typing import Any

from .model_client import complete
from .mongo_db import (
    get_episodes_collection,
    get_messages_collection,
    get_summaries_collection,
)


SHORT_TERM_N = int(os.environ.get("SHORT_TERM_N", "12"))
# Optional experiment-only cap used by the eviction/compression comparison.
# When set, older messages remain persisted in MongoDB but are excluded from
# the prompt window. This makes token savings measurable without destroying
# the underlying conversation history.
EVICTION_KEEP_N: int | None = None
SUMMARIZE_EVERY_USER_MSGS = int(
    os.environ.get("SUMMARIZE_EVERY_USER_MSGS", "5")
)
EPISODIC_TOP_K = int(os.environ.get("EPISODIC_TOP_K", "3"))
EMBEDDING_DIMENSIONS = 32

SYSTEM_PRIMER = (
    "You are a helpful municipal transit incident assistant. "
    "Use the supplied memory only as context, do not invent incident facts, "
    "and answer clearly and briefly."
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _estimate_tokens(text: str) -> int:
    """A transparent local estimate used for component-level accounting."""
    return max(1, math.ceil(len(text.split()) * 1.3)) if text.strip() else 0


def _hash_embedding(text: str) -> list[float]:
    """Create a deterministic local embedding without a hosted API.

    The vector is intentionally small and reproducible. It is sufficient for
    the cosine-similarity retrieval required by the local experiment.
    """
    vector = [0.0] * EMBEDDING_DIMENSIONS
    tokens = re.findall(r"[a-z0-9]+", text.casefold())
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS
        vector[index] += 1.0
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude:
        vector = [value / magnitude for value in vector]
    return vector


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return sum(left[i] * right[i] for i in range(size))


def _message_text(document: dict[str, Any]) -> str:
    return f"{document.get('role', 'unknown')}: {document.get('content', '')}"


def load_short_term_window(user_id: str, session_id: str | None) -> list[dict]:
    query: dict[str, Any] = {"user_id": user_id}
    if session_id is None:
        query["session_id"] = None
    else:
        query["session_id"] = session_id
    window_size = EVICTION_KEEP_N or SHORT_TERM_N
    documents = list(
        get_messages_collection()
        .find(query)
        .sort("created_at", -1)
        .limit(window_size)
    )
    documents.reverse()
    return documents


def load_latest_summaries(user_id: str, session_id: str | None) -> dict[str, dict | None]:
    collection = get_summaries_collection()
    session_summary = None
    if session_id is not None:
        session_summary = collection.find_one(
            {"user_id": user_id, "scope": "session", "session_id": session_id},
            sort=[("created_at", -1)],
        )
    lifetime_summary = collection.find_one(
        {"user_id": user_id, "scope": "user", "session_id": None},
        sort=[("created_at", -1)],
    )
    return {"session": session_summary, "lifetime": lifetime_summary}


def extract_episode_facts(message: str) -> list[tuple[str, float]]:
    """Extract up to three short, user-originated facts with simple scores."""
    candidates = [
        re.sub(r"\s+", " ", part).strip(" .!?\n")
        for part in re.split(r"[.!?\n]+", message)
    ]
    facts: list[tuple[str, float]] = []
    for candidate in candidates:
        words = candidate.split()
        if len(words) < 3:
            continue
        if len(candidate) > 240:
            candidate = candidate[:237].rstrip() + "..."
        importance = 0.8 if re.search(
            r"\b(i am|i'm|my goal|i need|i prefer|i work|remember)\b",
            candidate,
            re.IGNORECASE,
        ) else 0.5
        facts.append((candidate, importance))
        if len(facts) == 3:
            break
    return facts


def save_episode_facts(user_id: str, session_id: str | None, message: str) -> list[dict]:
    collection = get_episodes_collection()
    saved: list[dict] = []
    for fact, importance in extract_episode_facts(message):
        document = {
            "user_id": user_id,
            "session_id": session_id,
            "fact": fact,
            "importance": importance,
            "embedding": _hash_embedding(fact),
            "created_at": utc_now(),
        }
        result = collection.insert_one(document)
        document["_id"] = result.inserted_id
        saved.append(document)
    return saved


def retrieve_episodes(user_id: str, message: str, top_k: int = EPISODIC_TOP_K) -> list[dict]:
    query_vector = _hash_embedding(message)
    scored: list[tuple[float, dict]] = []
    for document in get_episodes_collection().find({"user_id": user_id}):
        score = cosine_similarity(query_vector, document.get("embedding", []))
        scored.append((score, document))
    scored.sort(key=lambda item: (item[0], item[1].get("created_at", utc_now())), reverse=True)
    results = []
    for score, document in scored[:top_k]:
        item = dict(document)
        item["similarity"] = round(score, 4)
        results.append(item)
    return results


def _summary_text(messages: list[dict]) -> str:
    bullets = []
    for document in messages[-8:]:
        role = document.get("role", "unknown")
        content = re.sub(r"\s+", " ", document.get("content", "")).strip()
        if content:
            bullets.append(f"- {role}: {content[:180]}")
    return "\n".join(bullets)


def _generate_summary(messages: list[dict], previous: str = "") -> tuple[str, dict]:
    conversation = "\n".join(_message_text(document) for document in messages)
    prompt = (
        "Summarize this transit-assistant conversation in concise bullet points. "
        "Preserve user goals, important preferences, and unresolved incident details. "
        f"Previous summary:\n{previous or 'None'}\n\nConversation:\n{conversation}"
    )
    try:
        result = complete(
            [
                {"role": "system", "content": "You create accurate memory summaries."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        text = result.get("content", "").strip()
        if text:
            return text, result
    except Exception:
        pass
    return _summary_text(messages), {
        "input_tokens": _estimate_tokens(prompt),
        "output_tokens": _estimate_tokens(_summary_text(messages)),
        "total_tokens": _estimate_tokens(prompt) + _estimate_tokens(_summary_text(messages)),
        "model": "fallback-summary",
    }


def maybe_create_summaries(user_id: str, session_id: str | None) -> list[dict]:
    if session_id is None:
        return []
    messages_collection = get_messages_collection()
    user_count = messages_collection.count_documents(
        {"user_id": user_id, "session_id": session_id, "role": "user"}
    )
    if user_count == 0 or user_count % SUMMARIZE_EVERY_USER_MSGS != 0:
        return []

    recent_messages = list(
        messages_collection.find(
            {"user_id": user_id, "session_id": session_id}
        ).sort("created_at", 1)
    )
    latest = get_summaries_collection().find_one(
        {"user_id": user_id, "scope": "session", "session_id": session_id},
        sort=[("created_at", -1)],
    )
    text, _ = _generate_summary(recent_messages, (latest or {}).get("text", ""))
    summary = {
        "user_id": user_id,
        "session_id": session_id,
        "scope": "session",
        "text": text,
        "created_at": utc_now(),
    }
    get_summaries_collection().insert_one(summary)

    if user_count % (SUMMARIZE_EVERY_USER_MSGS * 2) == 0:
        prior = list(
            get_summaries_collection()
            .find({"user_id": user_id, "scope": "session"})
            .sort("created_at", -1)
            .limit(10)
        )
        lifetime_text, _ = _generate_summary(
            [{"role": "summary", "content": item.get("text", "")} for item in prior]
        )
        lifetime = {
            "user_id": user_id,
            "session_id": None,
            "scope": "user",
            "text": lifetime_text,
            "created_at": utc_now(),
        }
        get_summaries_collection().insert_one(lifetime)
        return [summary, lifetime]
    return [summary]


def build_prompt(
    user_id: str,
    session_id: str | None,
    current_message: str,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    window = load_short_term_window(user_id, session_id)
    summaries = load_latest_summaries(user_id, session_id)
    episodes = retrieve_episodes(user_id, current_message)

    lifetime_text = (summaries["lifetime"] or {}).get("text", "")
    session_text = (summaries["session"] or {}).get("text", "")
    episodic_text = "\n".join(
        f"- {item.get('fact', '')} (similarity={item.get('similarity', 0):.2f})"
        for item in episodes
    ) or "None"
    window_text = "\n".join(_message_text(item) for item in window) or "None"
    long_term_text = f"Lifetime:\n{lifetime_text or 'None'}\nSession:\n{session_text or 'None'}"
    context_text = (
        f"Long-term summaries:\n{long_term_text}\n\n"
        f"Short-term window ({len(window)} messages):\n{window_text}\n\n"
        f"Episodic facts:\n{episodic_text}\n\n"
        f"Current user message:\n{current_message}"
    )
    prompt_messages = [
        {"role": "system", "content": SYSTEM_PRIMER},
        {"role": "user", "content": context_text},
    ]
    accounting = {
        "system_primer_tokens": _estimate_tokens(SYSTEM_PRIMER),
        "long_term_summary_tokens": _estimate_tokens(long_term_text),
        "short_term_window_tokens": _estimate_tokens(window_text),
        "episodic_fact_tokens": _estimate_tokens(episodic_text),
        "short_term_message_count": len(window),
        "short_term_messages": [
            {"role": item.get("role"), "content": item.get("content")} for item in window
        ],
        "long_term_summary": {
            "lifetime": lifetime_text or None,
            "session": session_text or None,
        },
        "episodic_facts": [
            {"fact": item.get("fact"), "similarity": item.get("similarity")} for item in episodes
        ],
    }
    return prompt_messages, accounting


def record_message(
    user_id: str,
    session_id: str | None,
    role: str,
    content: str,
) -> dict:
    document = {
        "user_id": user_id,
        "session_id": session_id,
        "role": role,
        "content": content,
        "created_at": utc_now(),
    }
    result = get_messages_collection().insert_one(document)
    document["_id"] = result.inserted_id
    return document

