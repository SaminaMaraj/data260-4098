"""Plain-Python tests for HW6 file-memory timestamps and /help."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.file_memory import (  # noqa: E402
    consolidation_required,
    handle_memory_command,
    read_last_consolidated_at,
)

NOW = datetime(2026, 10, 17, 6, 0, tzinfo=timezone.utc)


def memory_text(timestamp: datetime, fact_lines: int) -> str:
    header = [
        "# Consolidated Memory",
        f"<!-- last_consolidated_at: {timestamp.isoformat()} -->",
    ]
    facts = [f"- Fact {i}: transit project detail" for i in range(1, fact_lines + 1)]
    return "\n".join(header + facts) + "\n"


def test_timestamp_inside_comment_is_parsed() -> None:
    text = "<!-- last_consolidated_at: 2026-10-17T05:00:00+00:00 -->\n- fact one here"
    assert read_last_consolidated_at(text) == datetime(2026, 10, 17, 5, 0, tzinfo=timezone.utc)


def test_recent_and_short_memory_does_not_need_consolidation() -> None:
    text = memory_text(NOW - timedelta(hours=1), fact_lines=30)
    assert consolidation_required(text, now=NOW) is False


def test_old_timestamp_needs_consolidation() -> None:
    text = memory_text(NOW - timedelta(hours=25), fact_lines=30)
    assert consolidation_required(text, now=NOW) is True


def test_more_than_40_lines_needs_consolidation() -> None:
    text = memory_text(NOW - timedelta(hours=1), fact_lines=41)
    assert consolidation_required(text, now=NOW) is True


def test_help_explains_every_command(tmp_dir: Path) -> None:
    memory_path = tmp_dir / "MEMORY.md"
    memory_path.write_text("- Fact 1: transit project detail\n", encoding="utf-8")
    result = handle_memory_command("/help", memory_path=memory_path)
    commands = result["commands"]
    assert set(commands) == {"/memory", "/compact", "/dream", "/help"}
    assert all(isinstance(text, str) and len(text) > 20 for text in commands.values())


if __name__ == "__main__":
    import json
    import tempfile

    tests = [
        test_timestamp_inside_comment_is_parsed,
        test_recent_and_short_memory_does_not_need_consolidation,
        test_old_timestamp_needs_consolidation,
        test_more_than_40_lines_needs_consolidation,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    with tempfile.TemporaryDirectory() as tmp:
        test_help_explains_every_command(Path(tmp))
        print("PASS test_help_explains_every_command")
        help_path = Path(tmp) / "MEMORY.md"
        print(json.dumps(handle_memory_command("/help", memory_path=help_path), indent=2))
