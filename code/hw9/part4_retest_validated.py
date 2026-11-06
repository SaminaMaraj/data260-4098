"""HW9 Part 4.3/4.4: reject lesson_002 after the extra check and re-run Validated Improvement.
The extra check found a regression (x4 correct without lesson_002, wrong with it), so under
the 4.3 rule lesson_002 is rejected. Only the Validated Improvement variant depends on that
decision, so only it is re-run on test_data.json; the other three rows are unchanged."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.hw9_agents.system import (  # noqa: E402
    LessonStore,
    TwoAgentSystem,
    load_items,
    summarize,
)
from src.hw9_cache.config import STUDENT_NAME  # noqa: E402

RAW = ROOT / "reports" / "hw09" / "raw"
LESSON = "lesson_002"

print(
    f"{STUDENT_NAME} | part4_retest_validated.py | reject {LESSON}, re-run Validated Improvement",
    flush=True,
)
extra = json.loads((RAW / "part4_extra_lesson_check.json").read_text())
verdict = extra["verdict"]
if verdict["keep"]:
    raise SystemExit(f"extra check kept {LESSON}; nothing to change")

store = LessonStore()
lesson = next(x for x in store.lessons if x["lesson_id"] == LESSON)
lesson["status"] = "rejected"
lesson["extra_check"] = {
    "questions": [i["id"] for i in extra["items"]],
    "checks": verdict["checks"],
    "regressions": verdict["regressions"],
    "decision": "rejected: a correct answer became wrong with the lesson",
}
store.save()
print(f"{LESSON} -> status 'rejected' (regressions: {verdict['regressions']})")
print("lessons: " + ", ".join(f"{x['lesson_id']}={x['status']}" for x in store.lessons))

items = load_items("test_data.json")
print("\n=== Variant: Validated Improvement (kept lessons only) ===")
system = TwoAgentSystem(
    "real", repair=True, allow=lambda x: x["status"] == "kept", store=store
)
rows = system.run_set(items, "Validated Improvement")

old = json.loads((RAW / "part4_test.json").read_text())
final = {k: old[k] for k in ("Baseline", "Evaluator Repair", "Lesson Memory")}
final["Validated Improvement"] = {"summary": summarize(rows), "rows": rows}
(RAW / "part4_test_final.json").write_text(
    json.dumps(
        {
            "note": f"Validated Improvement re-run after rejecting {LESSON}; other variants from part4_test.json",
            "previous_validated_summary": old["Validated Improvement"]["summary"],
            **final,
        },
        indent=2,
        default=str,
    )
)

print(
    f"\n=== 4.4 Final results on test_data.json ({len(items)} held-out questions) ==="
)
print(
    f"{'Variant':<22} | {'Correct':>7} | {'Incorrect':>9} | {'Avg attempts':>12} | {'Avg latency (ms)':>16}"
)
print("-" * 78)
for name, d in final.items():
    s = d["summary"]
    print(
        f"{name:<22} | {s['correct']:>7} | {s['incorrect']:>9} | {s['avg_attempts']:>12.2f} | {s['avg_latency_ms']:>16.1f}"
    )
print(
    "\nLesson Memory = every saved lesson; Validated Improvement = kept lessons only (lesson_001)"
)
print(f"saved {RAW / 'part4_test_final.json'}")
