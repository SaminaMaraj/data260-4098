"""HW9 Part 4: revision loop, lesson memory, validation gate and the four variants.

Stopping condition: at most MAX_ATTEMPTS (2) answers per question. The loop stops
early on PASS; after the second attempt it stops and reports whatever the
Evaluator decided.
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

from src.hw9_agents.agents import AnsweringAgent, EvaluatorAgent, _json, _llm
from src.hw9_agents.reference import DATA_DIR, lookup, tokens

MAX_ATTEMPTS = 2
LESSONS_FILE = DATA_DIR / "lessons.json"
# words that appear in almost every domain question carry no signal for a trigger
GENERIC_WORDS = {
    "incident",
    "report",
    "reported",
    "staff",
    "agency",
    "transit",
    "vta",
    "long",
    "during",
    "new",
    "bus",
    "light-rail",
}
MIN_REPEATS = 2  # a failure pattern must be seen this many times to become a lesson

TEMPLATES = {
    "missing_value": (
        "The answer gives a generic or missing value instead of the agency-specific "
        "number or time limit from the reference dataset.",
        "Before answering a question about a time limit, threshold or other agency "
        "value, look it up in the reference dataset and state the exact value and unit.",
    ),
    "wrong_label": (
        "The answer uses its own wording instead of the exact labels or field names "
        "defined by the agency.",
        "Look up the reference dataset and list the exact category labels or field "
        "names as they are written there.",
    ),
    "unsupported_answer": (
        "The answer responds to a question outside the transit incident reference "
        "with general knowledge.",
        "If the reference dataset has no fact for the question, say that the question "
        "is outside the transit incident reference and do not answer it.",
    ),
    "evaluator_flagged": (
        "The answer contradicts or goes beyond the agency reference.",
        "Check the reference dataset and keep the answer consistent with it.",
    ),
}


def load_items(name: str) -> list[dict]:
    return json.loads((DATA_DIR / name).read_text())["items"]


# -------------------------------------------------------------------- lessons
class LessonStore:
    def __init__(self, path: Path = LESSONS_FILE):
        self.path = path
        self.lessons: list[dict] = json.loads(path.read_text()) if path.exists() else []

    def save(self) -> None:
        self.path.write_text(json.dumps(self.lessons, indent=2))

    def reset(self) -> None:
        self.lessons = []
        self.save()

    def by_type(self, failure_type: str) -> dict | None:
        return next(
            (x for x in self.lessons if x["failure_type"] == failure_type), None
        )

    def relevant(self, question: str, allow) -> list[tuple[dict, str]]:
        """Lessons whose trigger matches this question (loaded before answering).
        allow(lesson) -> bool decides which saved lessons this variant may use."""
        q = set(tokens(question))
        out = []
        for lesson in self.lessons:
            if not allow(lesson):
                continue
            trig = lesson["trigger"]
            if trig["type"] == "keywords":
                hit = sorted(q & set(trig["keywords"]))
                if hit:
                    out.append((lesson, "matched keywords: " + ", ".join(hit)))
            elif trig["type"] == "no_reference_match" and not lookup(question):
                out.append((lesson, "no reference fact matches the question"))
        return out

    def mark_used(self, lessons: list[dict]) -> None:
        for lesson in lessons:
            lesson["use_count"] += 1
        if lessons:
            self.save()

    def create(self, failure_type: str, failures: list[dict], llm: str) -> dict:
        pattern, correction = TEMPLATES.get(
            failure_type, TEMPLATES["evaluator_flagged"]
        )
        drafted_by = "template"
        if llm != "stub":
            examples = "\n".join(
                f"- Q: {f['question']}\n  A: {f['attempts'][0]['answer']}\n"
                f"  Evaluator: {f['attempts'][0]['evaluation']['explanation']}"
                for f in failures[:3]
            )
            data = _json(
                _llm(
                    "You are the Evaluator Agent. Several answers failed for the same reason. "
                    "Write ONE reusable lesson that applies to future questions of this kind. "
                    "Do not include any specific numbers or answers. Return ONLY JSON: "
                    '{"failure_pattern": "<one sentence>", "correction": "<one sentence '
                    'instruction for the Answering Agent>"}',
                    f"Failure type: {failure_type}\nFailed examples:\n{examples}",
                    json_mode=True,
                    llm=llm,
                )
            )
            if data.get("failure_pattern") and data.get("correction"):
                pattern, correction = data["failure_pattern"], data["correction"]
                drafted_by = "evaluator (qwen3:8b)"
        if failure_type == "unsupported_answer":
            trigger = {"type": "no_reference_match"}
        else:
            words = sorted(
                {w for f in failures for w in tokens(f["question"])} - GENERIC_WORDS
            )
            trigger = {"type": "keywords", "keywords": words}
        lesson = {
            "lesson_id": f"lesson_{len(self.lessons) + 1:03d}",
            "failure_pattern": pattern,
            "correction": correction,
            "created_at": date.today().isoformat(),
            "use_count": 0,
            "failure_type": failure_type,
            "action": "lookup_reference",
            "trigger": trigger,
            "source_questions": [f["id"] for f in failures],
            "drafted_by": drafted_by,
            "status": "candidate",
            "validation": None,
        }
        self.lessons.append(lesson)
        self.save()
        return lesson


# ----------------------------------------------------------------- the system
class TwoAgentSystem:
    def __init__(
        self,
        llm: str = "real",
        repair: bool = True,
        allow=None,
        store: LessonStore | None = None,
        verbose: bool = True,
    ):
        self.answering = AnsweringAgent(llm)
        self.evaluator = EvaluatorAgent(llm)
        self.repair = repair
        self.allow = allow  # None = this variant uses no lessons
        self.store = store
        self.verbose = verbose

    def say(self, msg: str) -> None:
        if self.verbose:
            print(msg, flush=True)

    def run(self, item: dict, forced_first_answer: str | None = None) -> dict:
        q, topic = item["question"], item["topic"]
        t0 = time.perf_counter()
        loaded = []
        if self.store is not None and self.allow is not None:
            loaded = self.store.relevant(q, self.allow)
            self.store.mark_used([lesson for lesson, _ in loaded])
        for lesson, reason in loaded:
            self.say(
                f"  LESSON LOADED {lesson['lesson_id']} ({lesson['failure_type']}; "
                f"{reason})"
            )
        lessons = [lesson for lesson, _ in loaded]

        attempts = []
        previous = feedback = None
        system_ms = 0.0
        for n in range(1, MAX_ATTEMPTS + 1):
            if n == 1 and forced_first_answer is not None:
                ans = {
                    "answer": forced_first_answer,
                    "lookup": None,
                    "lessons": [],
                    "ms": 0.0,
                    "forced": True,
                }
            else:
                ans = self.answering.answer(
                    q,
                    lessons=lessons,
                    use_lookup=bool(lessons)
                    or n > 1,  # a lesson or the feedback says so
                    previous=previous,
                    feedback=feedback,
                )
            ev = self.evaluator.evaluate(q, topic, ans["answer"])
            # the Baseline has no evaluator in its loop: its evaluation is scoring only
            system_ms += ans["ms"] + (ev["ms"] if self.repair else 0.0)
            attempts.append({"attempt": n, **ans, "evaluation": ev})
            self.say(f"  attempt {n}: {' '.join(ans['answer'].split())[:160]}")
            self.say(
                f"    evaluator: {ev['result']} ({ev['failure_type']}) "
                f"{ev['explanation'][:140]}"
            )
            if ev["result"] == "REVISE" and ev["feedback"]:
                self.say(f"    feedback: {ev['feedback'][:160]}")
            if ev["result"] == "PASS" or not self.repair:
                break
            previous, feedback = ans["answer"], ev["feedback"]
        final = attempts[-1]
        return {
            "id": item["id"],
            "question": q,
            "topic": topic,
            "lessons_loaded": [lesson["lesson_id"] for lesson in lessons],
            "attempts": attempts,
            "n_attempts": len(attempts),
            "first_result": attempts[0]["evaluation"]["result"],
            "final_result": final["evaluation"]["result"],
            "final_answer": final["answer"],
            "latency_ms": round(system_ms, 1),
            "wall_ms": round((time.perf_counter() - t0) * 1000, 1),
        }

    def run_set(self, items: list[dict], label: str) -> list[dict]:
        out = []
        for item in items:
            self.say(f"[{label}] {item['id']} ({item['topic']}): {item['question']}")
            out.append(self.run(item))
            self.say(
                f"  -> final {out[-1]['final_result']} after "
                f"{out[-1]['n_attempts']} attempt(s), {out[-1]['latency_ms']} ms\n"
            )
        return out


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    correct = sum(r["final_result"] == "PASS" for r in rows)
    return {
        "questions": n,
        "correct": correct,
        "incorrect": n - correct,
        "first_attempt_correct": sum(r["first_result"] == "PASS" for r in rows),
        "avg_attempts": round(sum(r["n_attempts"] for r in rows) / n, 2),
        "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / n, 1),
        "out_of_scope_unsupported": sum(
            r["topic"] == "out_of_scope" and r["final_result"] != "PASS" for r in rows
        ),
    }


def gate(before: list[dict], after: list[dict]) -> dict:
    """Validation rule from 4.3 (all three must hold to keep the lesson)."""
    b = {r["id"]: r for r in before}
    a = {r["id"]: r for r in after}
    fails_before = sum(r["first_result"] != "PASS" for r in before)
    fails_after = sum(r["first_result"] != "PASS" for r in after)
    regressions = [
        i
        for i in b
        if (b[i]["final_result"] == "PASS" and a[i]["final_result"] != "PASS")
        or (b[i]["first_result"] == "PASS" and a[i]["first_result"] != "PASS")
    ]
    oos_before = sum(
        r["topic"] == "out_of_scope" and r["final_result"] != "PASS" for r in before
    )
    oos_after = sum(
        r["topic"] == "out_of_scope" and r["final_result"] != "PASS" for r in after
    )
    checks = {
        "failures_improve_or_same": fails_after <= fails_before,
        "no_regression_on_correct": not regressions,
        "no_new_unsupported_answers": oos_after <= oos_before,
    }
    return {
        "first_attempt_failures_before": fails_before,
        "first_attempt_failures_after": fails_after,
        "regressions": regressions,
        "out_of_scope_unsupported_before": oos_before,
        "out_of_scope_unsupported_after": oos_after,
        "checks": checks,
        "keep": all(checks.values()),
    }
