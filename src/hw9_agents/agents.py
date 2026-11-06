"""HW9 Part 4: Answering Agent and Evaluator Agent.

Both agents use qwen3:8b through src/model_client.py (the same adapter as HW1-HW8).
llm="stub" replaces the model with deterministic text for the offline tests.

Communication: the two agents exchange plain dicts (no shared state):
  Answering -> Evaluator : {"question", "answer", "attempt"}
  Evaluator -> Answering : {"result": PASS|REVISE, "explanation", "feedback",
                            "failure_type"}
"""

from __future__ import annotations

import json
import re
import time

from src.hw9_agents.reference import (
    declines,
    fact_for_topic,
    load_reference,
    lookup,
    missing_terms,
)

NUMBER_WORDS = {
    "ten",
    "twenty",
    "thirty",
    "sixty",
    "four",
    "seven",
    "zero",
    "forty-eight",
    "one hour",
}
DOMAIN = "municipal transit incident operations at the s4098 Transit agency"


def _llm(system: str, user: str, *, json_mode: bool, llm: str) -> str:
    from src.model_client import complete

    out = complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.0,
        response_format="json" if json_mode else None,
    )
    return out["content"].strip()


def _json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).replace("```", "")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return {}
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return {}


# ----------------------------------------------------------------- Answering
class AnsweringAgent:
    def __init__(self, llm: str = "real"):
        self.llm = llm

    def answer(
        self,
        question: str,
        *,
        lessons: list[dict] | None = None,
        use_lookup: bool = False,
        previous: str | None = None,
        feedback: str | None = None,
    ) -> dict:
        """One answer attempt. Returns answer text, the reference lookup used, timing."""
        lessons = lessons or []
        t0 = time.perf_counter()
        refs = lookup(question) if use_lookup else None

        system = (
            f"You are the Answering Agent for {DOMAIN}. Answer the user's "
            "question directly in at most 60 words. Plain text."
        )
        if lessons:
            system += (
                "\n\nLessons from earlier evaluated mistakes (apply them):\n"
                + "\n".join(
                    f"- {lesson['lesson_id']}: {lesson['failure_pattern']} Correction: "
                    f"{lesson['correction']}"
                    for lesson in lessons
                )
            )
        user = f"Question: {question}"
        if refs is not None:
            if refs:
                user += "\n\nReference dataset lookup (agency facts):\n" + "\n".join(
                    f"- {r['fact']}" for r in refs
                )
            else:
                user += (
                    "\n\nReference dataset lookup: no reference fact covers this "
                    "question."
                )
        if previous is not None:
            user += (
                f"\n\nYour previous answer:\n{previous}\n\nEvaluator feedback:\n"
                f"{feedback}\n\nWrite a corrected answer."
            )

        if self.llm == "stub":
            text = self._stub(question, refs, lessons, previous)
        else:
            text = _llm(system, user, json_mode=False, llm=self.llm)
        return {
            "answer": text,
            "lookup": [r["topic"] for r in refs] if refs is not None else None,
            "lessons": [lesson["lesson_id"] for lesson in lessons],
            "ms": round((time.perf_counter() - t0) * 1000, 1),
        }

    @staticmethod
    def _stub(question, refs, lessons, previous) -> str:
        if refs:
            return refs[0]["fact"]
        if refs is not None:
            return "That question is outside the transit incident reference."
        return "Staff should follow the standard agency procedure for this situation."


# ----------------------------------------------------------------- Evaluator
class EvaluatorAgent:
    """Checks an answer against the reference dataset (ground truth).

    1. rule check: every required term group of the topic's fact must be in the
       answer; for out_of_scope topics the answer must decline.
    2. LLM check (qwen3:8b): compares the answer with the fact, writes the
       explanation and the correction feedback.
    PASS only if both agree. Feedback never contains the required values
    (they are masked), so the Answering Agent has to look them up itself.
    """

    def __init__(self, llm: str = "real"):
        self.llm = llm

    def evaluate(self, question: str, topic: str, answer: str) -> dict:
        t0 = time.perf_counter()
        fact = fact_for_topic(topic) if topic != "out_of_scope" else None
        if fact is None:
            rule_pass = declines(answer)
            missing = [] if rule_pass else [["<decline>"]]
            truth = load_reference()["out_of_scope_rule"]
            failure_type = "none" if rule_pass else "unsupported_answer"
        else:
            missing = missing_terms(answer, fact)
            rule_pass = not missing
            truth = fact["fact"]
            failure_type = "none"
            if missing:
                has_number = any(
                    any(ch.isdigit() for ch in v) for group in missing for v in group
                )
                failure_type = "missing_value" if has_number else "wrong_label"

        llm_verdict, explanation, feedback = "PASS" if rule_pass else "REVISE", "", ""
        if self.llm != "stub":
            raw = _llm(
                "You are the Evaluator Agent. Judge the Answering Agent's answer ONLY "
                "against the ground truth from the reference dataset. Extra general "
                "advice is fine if it does not contradict the ground truth. Return ONLY "
                'JSON: {"verdict": "PASS" or "REVISE", "explanation": "<one sentence>", '
                '"feedback": "<one sentence telling the Answering Agent what to fix; '
                'do not quote the exact value from the ground truth>"}',
                f"Question: {question}\nGround truth: {truth}\nAnswer: {answer}\n"
                f"Rule check: {'all required terms present' if rule_pass else 'FAILED'}",
                json_mode=True,
                llm=self.llm,
            )
            data = _json(raw)
            llm_verdict = str(data.get("verdict", "REVISE")).upper()
            if llm_verdict not in ("PASS", "REVISE"):
                llm_verdict = "REVISE"
            explanation = str(data.get("explanation", "")).strip()
            feedback = str(data.get("feedback", "")).strip()

        result = "PASS" if rule_pass and llm_verdict == "PASS" else "REVISE"
        if result == "REVISE" and failure_type == "none":
            failure_type = "evaluator_flagged"
        if not explanation:
            explanation = (
                "The answer matches the reference fact."
                if result == "PASS"
                else self._template_explanation(failure_type)
            )
        if result == "REVISE":
            feedback = self._mask(
                feedback or self._template_feedback(failure_type), fact
            )
            feedback += self._template_hint(failure_type)
        else:
            feedback = ""
        return {
            "result": result,
            "explanation": explanation,
            "feedback": feedback,
            "failure_type": failure_type,
            "rule_pass": rule_pass,
            "llm_verdict": llm_verdict,
            "missing_terms": missing,
            "ms": round((time.perf_counter() - t0) * 1000, 1),
        }

    @staticmethod
    def _mask(text: str, fact: dict | None) -> str:
        if fact is None:
            return text
        for group in fact["required_terms"]:
            for v in group:
                if any(ch.isdigit() for ch in v) or v.lower() in NUMBER_WORDS:
                    text = re.sub(
                        rf"(?<![\w.]){re.escape(v)}(?![\w])",
                        "[value]",
                        text,
                        flags=re.I,
                    )
        return text

    @staticmethod
    def _template_explanation(ft: str) -> str:
        return {
            "missing_value": "The answer does not state the agency-specific value from "
            "the reference dataset.",
            "wrong_label": "The answer does not use the exact labels or names defined in "
            "the reference dataset.",
            "unsupported_answer": "The question is outside the transit incident reference "
            "but the answer responds from general knowledge.",
        }.get(ft, "The answer does not match the reference fact.")

    @staticmethod
    def _template_feedback(ft: str) -> str:
        return {
            "missing_value": "State the exact agency value and unit for this rule.",
            "wrong_label": "Use the exact category labels / field names of the agency.",
            "unsupported_answer": "Say that the question is outside the transit incident "
            "reference instead of answering it.",
        }.get(ft, "Correct the answer so it matches the agency rule.")

    @staticmethod
    def _template_hint(ft: str) -> str:
        if ft == "unsupported_answer":
            return " Only answer questions that the transit incident reference covers."
        return " Check the reference dataset before answering."
