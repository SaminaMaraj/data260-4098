"""Run the HW6 short-term-memory and eviction comparison."""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import yaml

import src.hw6_memory as memory
from src.hw6_memory_api import ChatRequest, chat
from src.mongo_db import get_messages_collection

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "reports" / "hw06" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

CONVERSATION = [
    "My project tracks municipal transit incidents.",
    "I am studying how delays affect passengers.",
    "I prefer concise answers with one practical example.",
    "The main route I mentioned is VTA Route 22.",
    "My goal is to build a reliable incident assistant.",
    "I find episodic memory retrieval difficult.",
    "Please remember that my project uses MongoDB.",
    "A useful category is service-suspension.",
    "I want to compare memory sizes fairly.",
    "The assistant should not invent incident details.",
] * 3


def score_probe(reply: str, expected: list[str]) -> int:
    lowered = reply.casefold()
    hits = sum(1 for term in expected if term.casefold() in lowered)
    return min(5, max(1, 1 + hits))


def run_setting(label: str, n: int, compress: bool = False) -> dict:
    memory.SHORT_TERM_N = n
    user_id = f"hw6_{label}_{int(time.time())}"
    session_id = f"session_{label}"
    turns = []
    for index, message in enumerate(CONVERSATION, start=1):
        started = time.perf_counter()
        result = chat(ChatRequest(user_id=user_id, session_id=session_id, message=message))
        used = result["memory_used"]
        turns.append({
            "setting": label,
            "turn": index,
            "prompt_tokens": used.get("prompt_tokens", 0),
            "completion_tokens": used.get("completion_tokens", 0),
            "system_primer_tokens": used.get("system_primer_tokens", 0),
            "long_term_summary_tokens": used.get("long_term_summary_tokens", 0),
            "short_term_window_tokens": used.get("short_term_window_tokens", 0),
            "episodic_fact_tokens": used.get("episodic_fact_tokens", 0),
            "latency_ms": used.get("latency_ms", round((time.perf_counter() - started) * 1000, 2)),
        })

    if compress:
        collection = get_messages_collection()
        documents = list(collection.find({"user_id": user_id, "session_id": session_id}).sort("created_at", -1))
        for document in documents[12:]:
            collection.delete_one({"_id": document["_id"]})

    probes = yaml.safe_load((ROOT / "memory_probes.yaml").read_text(encoding="utf-8"))["probes"]
    probe_results = []
    for probe in probes:
        result = chat(ChatRequest(user_id=user_id, session_id=session_id, message=probe["question"]))
        probe_results.append({
            "setting": label,
            "probe_id": probe["id"],
            "score": score_probe(result["reply"], probe["expected_criteria"]),
            "reply": result["reply"],
        })
    return {"turns": turns, "probes": probe_results}


def main() -> None:
    results = [
        run_setting("SHORT_TERM_N=4", 4),
        run_setting("SHORT_TERM_N=12", 12),
        run_setting("SHORT_TERM_N=30", 30),
        run_setting("eviction_keep_12", 30, compress=True),
    ]
    turns = [row for result in results for row in result["turns"]]
    probes = [row for result in results for row in result["probes"]]
    (RAW / "memory_turns.json").write_text(json.dumps(turns, indent=2), encoding="utf-8")
    (RAW / "memory_probes.json").write_text(json.dumps(probes, indent=2), encoding="utf-8")
    with (RAW / "memory_turns.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=turns[0].keys())
        writer.writeheader()
        writer.writerows(turns)

    summary = []
    for label in sorted({row["setting"] for row in turns}):
        setting_turns = [row for row in turns if row["setting"] == label]
        setting_probes = [row["score"] for row in probes if row["setting"] == label]
        summary.append({
            "setting": label,
            "mean_prompt_tokens": round(sum(row["prompt_tokens"] for row in setting_turns) / len(setting_turns), 2),
            "mean_completion_tokens": round(sum(row["completion_tokens"] for row in setting_turns) / len(setting_turns), 2),
            "mean_latency_ms": round(sum(row["latency_ms"] for row in setting_turns) / len(setting_turns), 2),
            "mean_probe_quality": round(sum(setting_probes) / len(setting_probes), 2),
        })
    for row in summary:
        input_tokens = row["mean_prompt_tokens"] * 30 * 10000
        output_tokens = row["mean_completion_tokens"] * 30 * 10000
        row["estimated_cost_10000_conversations"] = round(
            input_tokens / 1_000_000 + output_tokens * 5 / 1_000_000,
            4,
        )
    best = max(summary, key=lambda row: (row["mean_probe_quality"], -row["mean_prompt_tokens"]))
    worst = min(summary, key=lambda row: (row["mean_probe_quality"], -row["mean_prompt_tokens"]))
    comparison = {"settings": summary, "best_setting": best["setting"], "worst_setting": worst["setting"]}
    (RAW / "memory_cost_summary.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
