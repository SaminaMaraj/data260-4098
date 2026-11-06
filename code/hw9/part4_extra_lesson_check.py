"""HW9 Part 4.3 extra check: test lesson_002 on new questions that actually load it.

    python code/hw9/part4_extra_lesson_check.py

In the validation run no validation question matched lesson_002's keywords, so
the gate kept it without testing it. This check uses 5 NEW questions (not in the
training, validation or test files) that do load lesson_002 and runs each one
twice with the Evaluator Repair system:
  before = kept lessons without lesson_002
  after  = kept lessons with lesson_002
and applies the same three keep/reject checks as the validation gate.
This is an extra check run after validation; it does not change the datasets
or the earlier gate decision. lessons.json is not modified (a temporary copy is
used, so use_count stays the same).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.hw9_agents.system import (  # noqa: E402
    LESSONS_FILE,
    LessonStore,
    TwoAgentSystem,
    gate,
    summarize,
)
from src.hw9_cache.config import STUDENT_NAME  # noqa: E402

RAW = ROOT / "reports" / "hw09" / "raw"
LESSON = "lesson_002"

# new questions written for this check; topic = which reference fact is ground truth
ITEMS = [
    {
        "id": "x1",
        "topic": "required_fields",
        "question": "Which fields must be filled in when submitting an incident report?",
    },
    {
        "id": "x2",
        "topic": "valid_categories",
        "question": "What category labels are allowed for a transit incident?",
    },
    {
        "id": "x3",
        "topic": "related_types",
        "question": "What types of notes are allowed to be attached to an incident?",
    },
    {
        "id": "x4",
        "topic": "out_of_scope",
        "question": "Which pets are allowed on trains?",
    },
    {
        "id": "x5",
        "topic": "out_of_scope",
        "question": "Is food allowed on light-rail trains?",
    },
]


def main(llm: str) -> int:
    print(
        f"{STUDENT_NAME} | part4_extra_lesson_check.py | extra check of {LESSON}",
        flush=True,
    )
    tmp = Path(tempfile.mkdtemp()) / "lessons.json"
    shutil.copy(LESSONS_FILE, tmp)
    store = LessonStore(tmp)
    kept = {x["lesson_id"] for x in store.lessons if x["status"] == "kept"}
    if LESSON not in kept:
        raise SystemExit(f"{LESSON} is not a kept lesson")
    without = kept - {LESSON}

    for it in ITEMS:
        hit = [
            lesson["lesson_id"]
            for lesson, _ in store.relevant(it["question"], lambda x: True)
        ]
        print(f"{it['id']} ({it['topic']}): {it['question']}  -> loads {hit}")

    print(f"\n--- before: kept lessons without {LESSON} {sorted(without)} ---")
    before = TwoAgentSystem(
        llm, repair=True, allow=lambda x: x["lesson_id"] in without, store=store
    ).run_set(ITEMS, "before")
    print(f"\n--- after: kept lessons with {LESSON} {sorted(kept)} ---")
    after = TwoAgentSystem(
        llm, repair=True, allow=lambda x: x["lesson_id"] in kept, store=store
    ).run_set(ITEMS, "after")

    verdict = gate(before, after)
    print(f"\n=== Extra check of {LESSON} on {len(ITEMS)} new questions ===")
    print(
        f"{'id':<4} {'topic':<18} {'lesson_002 loaded':<18} "
        f"{'before (1st/final, tries)':<27} after (1st/final, tries)"
    )
    for b, a in zip(before, after):
        print(
            f"{b['id']:<4} {b['topic']:<18} {str(LESSON in a['lessons_loaded']):<18} "
            f"{b['first_result'] + '/' + b['final_result'] + ', ' + str(b['n_attempts']):<27} "
            f"{a['first_result']}/{a['final_result']}, {a['n_attempts']}"
        )
    sb, sa = summarize(before), summarize(after)
    print(
        f"\nFirst-try correct: {sb['first_attempt_correct']}/{len(ITEMS)} -> "
        f"{sa['first_attempt_correct']}/{len(ITEMS)}"
    )
    print(
        f"Final correct:     {sb['correct']}/{len(ITEMS)} -> {sa['correct']}/{len(ITEMS)}"
    )
    print(f"Average attempts:  {sb['avg_attempts']:.2f} -> {sa['avg_attempts']:.2f}")
    print(f"Checks: {verdict['checks']}")
    print(
        f"Result: {LESSON} {'still passes (keep)' if verdict['keep'] else 'FAILS (would be rejected)'}"
    )

    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / "part4_extra_lesson_check.json"
    out.write_text(
        json.dumps(
            {
                "lesson": LESSON,
                "items": ITEMS,
                "verdict": verdict,
                "summary_before": sb,
                "summary_after": sa,
                "before": before,
                "after": after,
            },
            indent=2,
            default=str,
        )
    )
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("stub" if "--stub" in sys.argv else "real"))
