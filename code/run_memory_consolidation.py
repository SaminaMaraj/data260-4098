"""Create and consolidate the required 55-line HW6 memory fixture."""

from __future__ import annotations

import json
from pathlib import Path

from src.file_memory import compact_memory, memory_line_count


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "reports" / "hw06" / "raw"


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    original_path = RAW / "MEMORY.original.md"
    consolidated_path = RAW / "MEMORY.consolidated.md"

    # Three realistic facts are repeated: 8 + 7 + 7 copies = 19 duplicate lines.
    repeated_facts = [
        ("- Route 22 has frequent afternoon delays", 8),
        ("- Main incident categories include delay and collision", 7),
        ("- Reliable transit analysis is an important project goal", 7),
    ]
    unique_facts = [
        "- The project tracks municipal transit incidents for VTA routes",
        "- Incidents are stored in the s4098_doc MongoDB database",
        "- The FastAPI backend runs on port 8498",
        "- Incident titles are limited to 100 characters",
        "- Incident status values are open, investigating, and resolved",
        "- Service-suspension incidents need a clear route line",
        "- Infrastructure issues include signal and track problems",
        "- Diridon Station had a signal problem in the sample data",
        "- The VTA Green Line appears in the sample incident",
        "- Delays are analyzed by route line and time of day",
        "- The user studies how delays affect passengers",
        "- The user prefers one practical example per answer",
        "- Episodic facts are retrieved by cosine similarity",
        "- Embeddings use a deterministic SHA-256 hashed vector",
        "- Session summaries are created every five user messages",
        "- Lifetime summaries condense recent session summaries",
        "- The short-term window keeps the latest messages",
        "- Memory is scoped by user_id and session_id",
        "- The assistant must not invent incident details",
        "- Experiments compare short-term window sizes 4, 12, and 30",
        "- Probe questions are scored on a 1-5 rubric",
        "- The local model runs through Ollama",
        "- AGENT.md stores durable project instructions",
        "- MEMORY.md stores durable facts from conversations",
        "- Secrets and API keys must never be committed",
        "- HW1-HW5 behavior must remain compatible",
        "- Reproducible runs use SID4 4098",
    ]
    contradictory_facts = [
        "- Response preference: concise",
        "- Response preference: detailed",
        "- Preferred model: qwen3:8b",
        "- Preferred model: qwen3:4b",
        "- Project status: active",
        "- Project status: paused",
    ]
    lines = [fact for fact, _ in repeated_facts] + unique_facts + contradictory_facts
    for fact, copies in repeated_facts:
        lines += [fact] * (copies - 1)
    assert len(lines) == 55
    original_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = compact_memory(original_path, consolidated_path)
    result["original_file"] = str(original_path)
    result["consolidated_file"] = str(consolidated_path)
    result["original_line_count_check"] = memory_line_count(original_path.read_text(encoding="utf-8"))
    result["under_40_check"] = result["after_lines"] < 40
    (RAW / "memory_consolidation_results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
