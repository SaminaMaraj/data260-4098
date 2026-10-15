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

    unique_facts = [f"- Fact {index}: municipal transit project detail" for index in range(1, 31)]
    duplicate_facts = ["- Fact 1: municipal transit project detail"] * 12
    contradictory_facts = [
        "- Response preference: concise",
        "- Response preference: detailed",
        "- Preferred model: qwen3:8b",
        "- Preferred model: qwen3:4b",
        "- Project status: active",
        "- Project status: paused",
    ]
    additional_duplicates = ["- Fact 2: municipal transit project detail"] * 7
    lines = unique_facts + duplicate_facts + contradictory_facts + additional_duplicates
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
