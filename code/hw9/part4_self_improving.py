"""HW9 Part 4: self-improving two-agent system (Answering Agent + Evaluator Agent).

    python code/hw9/part4_self_improving.py demo-revision  # 4.1 controlled revision case
    python code/hw9/part4_self_improving.py train          # 4.2 mine lessons on training_data
    python code/hw9/part4_self_improving.py validate       # 4.3 keep/reject each lesson
    python code/hw9/part4_self_improving.py reuse-demo     # 4.2 a later question reuses a lesson
    python code/hw9/part4_self_improving.py test           # 4.4 four variants on test_data
    python code/hw9/part4_self_improving.py all            # train -> validate -> reuse-demo -> test

Add --llm stub for an offline dry run (no Ollama). Raw results go to
reports/hw09/raw/part4_*.json; lessons live in code/hw9/part4_datasets/lessons.json.
test_data.json is only read by the `test` command.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.hw9_agents.system import (  # noqa: E402
    MIN_REPEATS,
    LessonStore,
    TwoAgentSystem,
    gate,
    load_items,
    summarize,
)
from src.hw9_cache.config import STUDENT_NAME  # noqa: E402

RAW = ROOT / "reports" / "hw09" / "raw"
ALL = lambda lesson: True  # noqa: E731
KEPT = lambda lesson: lesson["status"] == "kept"  # noqa: E731


def banner(cmd: str, llm: str) -> None:
    print(
        f"{STUDENT_NAME} | part4_self_improving.py {cmd} | model="
        f"{'qwen3:8b via model_client' if llm == 'real' else 'STUB'}",
        flush=True,
    )


def save(name: str, obj) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / name).write_text(json.dumps(obj, indent=2, default=str))
    print(f"saved {RAW / name}")


# ------------------------------------------------------------------ 4.1
def demo_revision(args) -> None:
    item = next(i for i in load_items("training_data.json") if i["id"] == "tr01")
    forced = "A bus bridge can be requested when a light-rail suspension is long."
    print("\n=== 4.1 Controlled revision case ===")
    print(f"Question: {item['question']}")
    print(
        f"Controlled initial answer (intentionally incomplete, no time limit): {forced}\n"
    )
    system = TwoAgentSystem(args.llm, repair=True)
    res = system.run(item, forced_first_answer=forced)
    print("\n--- Revision sequence ---")
    for a in res["attempts"]:
        ev = a["evaluation"]
        print(f"Attempt {a['attempt']} answer: {a['answer']}")
        if a.get("lookup") is not None:
            print(f"  reference lookup used: {a['lookup']}")
        print(
            f"  Evaluator result: {ev['result']}  failure_type={ev['failure_type']}  "
            f"rule_pass={ev['rule_pass']}  llm_verdict={ev['llm_verdict']}"
        )
        print(f"  Explanation: {ev['explanation']}")
        if ev["feedback"]:
            print(f"  Feedback: {ev['feedback']}")
    print(f"\nNumber of attempts: {res['n_attempts']} (max 2)")
    print(f"Final evaluation:   {res['final_result']}")
    print(f"Final response:     {res['final_answer']}")
    save("part4_revision_demo.json", {"forced_initial_answer": forced, **res})


# ------------------------------------------------------------------ 4.2
def train(args) -> None:
    store = LessonStore()
    if not args.keep_lessons:
        store.reset()
    print(
        f"\n=== 4.2 Training run: Evaluator Repair + lesson memory "
        f"(a lesson is created after {MIN_REPEATS} first-attempt failures of the same "
        "type) ===\n"
    )
    system = TwoAgentSystem(args.llm, repair=True, allow=ALL, store=store)
    failures: dict[str, list] = {}
    rows, events = [], []
    for item in load_items("training_data.json"):
        print(f"[train] {item['id']} ({item['topic']}): {item['question']}")
        res = system.run(item)
        rows.append(res)
        ft = res["attempts"][0]["evaluation"]["failure_type"]
        if res["first_result"] != "PASS":
            failures.setdefault(ft, []).append(res)
            if len(failures[ft]) >= MIN_REPEATS and store.by_type(ft) is None:
                lesson = store.create(ft, failures[ft], args.llm)
                events.append({"after": item["id"], "lesson": lesson})
                print(
                    f"  ** LESSON CREATED {lesson['lesson_id']} for repeated failure "
                    f"'{ft}' (seen in {lesson['source_questions']})"
                )
                print(f"     failure_pattern: {lesson['failure_pattern']}")
                print(f"     correction:      {lesson['correction']}")
                print(f"     trigger:         {lesson['trigger']}")
        print(
            f"  -> final {res['final_result']} after {res['n_attempts']} attempt(s)\n"
        )
    reused = [r for r in rows if r["lessons_loaded"]]
    print("=== Lessons reused later in the training run ===")
    for r in reused:
        print(
            f"  {r['id']}: loaded {r['lessons_loaded']} -> first attempt "
            f"{r['first_result']}, final {r['final_result']}"
        )
    print(f"\nlessons.json now has {len(store.lessons)} lesson(s)")
    save(
        "part4_training.json",
        {"rows": rows, "lesson_events": events, "summary": summarize(rows)},
    )


# ------------------------------------------------------------------ 4.3
def validate(args) -> None:
    store = LessonStore()
    if not store.lessons:
        raise SystemExit("no lessons yet - run `train` first")
    items = load_items("validation_data.json")
    print("\n=== 4.3 Validation gate (validation_data.json) ===")
    kept_ids: set[str] = set()
    for lesson in store.lessons:
        lesson["status"] = "candidate"
    store.save()
    print("\n--- before: system with no lessons ---")
    before = TwoAgentSystem(
        args.llm, repair=True, allow=lambda x: False, store=store
    ).run_set(items, "val-before")
    report = {"baseline_before": summarize(before), "lessons": []}
    for lesson in store.lessons:
        lid = lesson["lesson_id"]
        print(f"\n--- after: kept lessons {sorted(kept_ids)} + candidate {lid} ---")
        allow = lambda x, ids=kept_ids | {lid}: x["lesson_id"] in ids  # noqa: E731
        after = TwoAgentSystem(args.llm, repair=True, allow=allow, store=store).run_set(
            items, f"val+{lid}"
        )
        verdict = gate(before, after)
        lesson["status"] = "kept" if verdict["keep"] else "rejected"
        lesson["validation"] = {
            **verdict,
            "summary_before": summarize(before),
            "summary_after": summarize(after),
        }
        store.save()
        print(
            f"  GATE {lid}: first-attempt failures {verdict['first_attempt_failures_before']}"
            f" -> {verdict['first_attempt_failures_after']}, regressions="
            f"{verdict['regressions']}, unsupported out-of-scope "
            f"{verdict['out_of_scope_unsupported_before']} -> "
            f"{verdict['out_of_scope_unsupported_after']}  => "
            f"{'KEEP' if verdict['keep'] else 'REJECT (removed from the validated system)'}"
        )
        report["lessons"].append(
            {"lesson_id": lid, "verdict": verdict, "before": before, "after": after}
        )
        if verdict["keep"]:
            kept_ids.add(lid)
            before = after  # the next candidate is compared with the improved system
    print(f"\nKept lessons: {sorted(kept_ids) or 'none'}")
    save("part4_validation.json", report)


def reuse_demo(args) -> None:
    store = LessonStore()
    item = next(i for i in load_items("validation_data.json") if i["id"] == args.item)
    print("\n=== 4.2 Lesson reuse on a later related question ===")
    for lesson in store.lessons:
        print(
            f"saved {lesson['lesson_id']} ({lesson['status']}, created "
            f"{lesson['created_at']} from {lesson['source_questions']}, "
            f"use_count={lesson['use_count']}): {lesson['correction']}"
        )
    print(f"\nNew question {item['id']}: {item['question']}")
    res = TwoAgentSystem(args.llm, repair=True, allow=ALL, store=store).run(item)
    print(f"\nLessons loaded before answering: {res['lessons_loaded'] or 'none'}")
    print(f"Reference lookup on attempt 1: {res['attempts'][0].get('lookup')}")
    print(
        f"Result: {res['first_result']} on attempt 1, final {res['final_result']} "
        f"after {res['n_attempts']} attempt(s)"
    )
    print(f"Answer: {res['final_answer']}")
    print(
        "use_count now: "
        + ", ".join(f"{x['lesson_id']}={x['use_count']}" for x in LessonStore().lessons)
    )
    save("part4_reuse_demo.json", res)


# ------------------------------------------------------------------ 4.4
def test(args) -> None:
    store = LessonStore()
    items = load_items("test_data.json")
    variants = [
        ("Baseline", TwoAgentSystem(args.llm, repair=False)),
        ("Evaluator Repair", TwoAgentSystem(args.llm, repair=True)),
        (
            "Lesson Memory",
            TwoAgentSystem(args.llm, repair=True, allow=ALL, store=store),
        ),
        (
            "Validated Improvement",
            TwoAgentSystem(args.llm, repair=True, allow=KEPT, store=store),
        ),
    ]
    results = {}
    for name, system in variants:
        print(f"\n=== Variant: {name} ===")
        rows = system.run_set(items, name)
        results[name] = {"summary": summarize(rows), "rows": rows}
    print(f"\n=== 4.4 Results on test_data.json ({len(items)} held-out questions) ===")
    print(
        f"{'Variant':<22} | {'Correct':>7} | {'Incorrect':>9} | {'Avg attempts':>12} | "
        f"{'Avg latency (ms)':>16}"
    )
    print("-" * 78)
    for name, _ in variants:
        s = results[name]["summary"]
        print(
            f"{name:<22} | {s['correct']:>7} | {s['incorrect']:>9} | "
            f"{s['avg_attempts']:>12.2f} | {s['avg_latency_ms']:>16.1f}"
        )
    print(
        "\nLessons used: Lesson Memory = every saved lesson; Validated Improvement = "
        "only lessons with status 'kept': "
        + ", ".join(f"{x['lesson_id']}={x['status']}" for x in store.lessons)
    )
    save("part4_test.json", results)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "command",
        choices=["demo-revision", "train", "validate", "reuse-demo", "test", "all"],
    )
    p.add_argument("--llm", choices=["real", "stub"], default="real")
    p.add_argument(
        "--keep-lessons",
        action="store_true",
        help="train: do not reset lessons.json first",
    )
    p.add_argument("--item", default="va01", help="reuse-demo: validation item id")
    args = p.parse_args()
    banner(args.command, args.llm)
    steps = {
        "demo-revision": [demo_revision],
        "train": [train],
        "validate": [validate],
        "reuse-demo": [reuse_demo],
        "test": [test],
        "all": [train, validate, reuse_demo, test],
    }[args.command]
    for step in steps:
        step(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
