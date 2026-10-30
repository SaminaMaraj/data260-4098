"""Planner, Writer and Reviewer logic (what each agent does with one message).

The Kafka plumbing is in agent_runtime.py; these functions only turn an input
message into an output message. --llm stub replaces the model call with a
deterministic answer (used by the Part 3 tests and the verify script, where
the subject is Kafka behavior, not the model).
"""

from __future__ import annotations

import asyncio
import json
import os
import re

from src.hw8_kafka.agent_runtime import AgentContext, PoisonMessage

os.environ.setdefault("MODEL_MAX_TOKENS", "400")
MODEL = os.environ.get("SMOL_MODEL", "qwen3:8b")

DOMAIN = (
    "municipal transit incidents (bus/light-rail delays, collisions, "
    "service suspensions, infrastructure issues)"
)


def _json_object(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("model did not return a JSON object")
    return json.loads(cleaned[start : end + 1])


async def _chat(system: str, user: str, *, json_mode: bool) -> str:
    from src.model_client import complete  # imported lazily: stub mode needs no Ollama

    result = await asyncio.to_thread(
        complete,
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        model=MODEL,
        temperature=0.0,
        response_format="json" if json_mode else None,
    )
    return result["content"]


async def _stub_work(ctx: AgentContext, message: dict) -> None:
    # the ordering test sets a per-message work time (seeded with VERIFY_SEED)
    seconds = message.get("work_ms", ctx.work_seconds * 1000) / 1000
    if seconds:
        await asyncio.sleep(seconds)


# ------------------------------------------------------------------ Planner
async def plan(message: dict, ctx: AgentContext) -> dict:
    question = message.get("question")
    if not isinstance(question, str) or not question.strip():
        raise PoisonMessage("inbox message has no question")
    if ctx.llm == "stub":
        await _stub_work(ctx, message)
        steps = [
            "Identify the incident type and who is affected",
            "List the immediate actions in time order",
            "Name what to communicate to riders",
        ]
        return {
            "question": question,
            "plan": {"steps": steps, "focus": "transit operations"},
        }

    raw = await _chat(
        f"You are the Planner in a 3-agent team about {DOMAIN}. "
        'Return ONLY JSON: {"steps": [3 or 4 short instructions for the Writer], '
        '"focus": "<one phrase>"}. Do not answer the question yourself.',
        f"Question: {question}",
        json_mode=True,
    )
    data = _json_object(raw)
    steps = [str(s).strip() for s in data.get("steps", []) if str(s).strip()][:4]
    if len(steps) < 2:
        raise ValueError(f"planner returned too few steps: {raw[:200]}")
    return {
        "question": question,
        "plan": {"steps": steps, "focus": str(data.get("focus", ""))},
    }


# ------------------------------------------------------------------- Writer
def check_task(message: dict) -> tuple[str, list[str]]:
    """Schema check for a task message; a bad one is a poison message."""
    plan_value = message.get("plan")
    if not isinstance(plan_value, dict):
        raise PoisonMessage("task has no valid 'plan' object")
    steps = plan_value.get("steps")
    if (
        not isinstance(steps, list)
        or not steps
        or not all(isinstance(s, str) for s in steps)
    ):
        raise PoisonMessage("plan.steps must be a non-empty list of strings")
    return str(message.get("question", "")), steps


async def write(message: dict, ctx: AgentContext) -> dict:
    question, steps = check_task(message)
    if ctx.llm == "stub":
        await _stub_work(ctx, message)
        draft = f"Draft for: {question or message.get('incident_id')} - " + "; ".join(
            steps
        )
        return {
            "question": question,
            "plan": message["plan"],
            "draft": draft,
            **{k: message[k] for k in ("incident_id", "seq") if k in message},
        }

    numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1))
    draft = await _chat(
        f"You are the Writer in a 3-agent team about {DOMAIN}. Follow the plan and "
        "write a clear, practical answer in at most 150 words. Plain text, no "
        "headings.",
        f"Question: {question}\nPlan:\n{numbered}",
        json_mode=False,
    )
    draft = draft.strip()
    if not draft:
        raise ValueError("writer produced an empty draft")
    return {"question": question, "plan": message["plan"], "draft": draft}


# ----------------------------------------------------------------- Reviewer
async def review(message: dict, ctx: AgentContext) -> dict:
    draft = message.get("draft")
    if not isinstance(draft, str) or not draft.strip():
        raise PoisonMessage("draft message has no draft text")
    question = message.get("question", "")
    if ctx.llm == "stub":
        await _stub_work(ctx, message)
        return {
            "status": "approved",
            "answer": draft,
            "review": "stub review: ok",
            "question": question,
        }

    raw = await _chat(
        f"You are the Reviewer in a 3-agent team about {DOMAIN}. Check that the draft "
        "answers the question, is accurate, practical and at most 150 words. Return "
        "ONLY "
        'JSON: {"approved": true or false, "feedback": "<one sentence>"}.',
        f"Question: {question}\nDraft:\n{draft}",
        json_mode=True,
    )
    data = _json_object(raw)
    approved = data.get("approved") is True
    return {
        "status": "approved" if approved else "needs_revision",
        "answer": draft,
        "review": str(data.get("feedback", "")).strip(),
        "question": question,
    }
