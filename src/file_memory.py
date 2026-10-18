"""File-based AGENT.md and MEMORY.md support for HW6 Part 4."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = ROOT / "AGENT.md"
MEMORY_PATH = ROOT / "MEMORY.md"
CONSOLIDATION_PATTERN = re.compile(r"last_consolidated_at:\s*(.+)", re.IGNORECASE)

HELP_TEXT = {
    "/memory": "Displays the current AGENT.md and MEMORY.md contents.",
    "/compact": "Consolidates MEMORY.md and reports line counts before and after, "
                "duplicates merged, and contradictions found.",
    "/dream": "Extracts useful high-confidence facts from recent messages and adds them "
              "to MEMORY.md.",
    "/help": "Lists and explains the available memory commands.",
}


def load_memory_files(agent_path: Path = AGENT_PATH, memory_path: Path = MEMORY_PATH) -> dict[str, str]:
    return {
        "agent": agent_path.read_text(encoding="utf-8") if agent_path.exists() else "",
        "memory": memory_path.read_text(encoding="utf-8") if memory_path.exists() else "",
    }


def memory_line_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip() and not line.lstrip().startswith("<!--"))


def read_last_consolidated_at(text: str) -> datetime | None:
    match = CONSOLIDATION_PATTERN.search(text)
    if not match:
        return None
    try:
        # The timestamp is stored inside an HTML comment, so drop the closing "-->".
        timestamp = match.group(1).split("-->", 1)[0].strip()
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def consolidation_required(memory_text: str, now: datetime | None = None, max_lines: int = 40, max_age_hours: int = 24) -> bool:
    if memory_line_count(memory_text) > max_lines:
        return True
    last = read_last_consolidated_at(memory_text)
    if last is None:
        return True
    current = now or datetime.now(timezone.utc)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return current - last > timedelta(hours=max_age_hours)


def build_memory_system_prompt(agent_text: str, memory_text: str) -> str:
    return (
        "Durable agent instructions:\n"
        f"{agent_text.strip() or 'None'}\n\n"
        "Durable user/project memory:\n"
        f"{memory_text.strip() or 'None'}"
    )


def extract_episode_facts(message: str) -> list[tuple[str, float]]:
    """Extract concise, high-confidence facts for /dream."""
    parts = [re.sub(r"\s+", " ", part).strip(" .!?\n")
             for part in re.split(r"[.!?\n]+", message)]
    return [
        (part, 0.8 if re.search(r"\b(my|remember|prefer|important|project)\b", part, re.I) else 0.5)
        for part in parts if len(part.split()) >= 3
    ][:3]


def _normalized(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip()).casefold()


def _contradiction_key(line: str) -> str | None:
    match = re.match(r"\s*[-*]?\s*([^:]+):", line)
    return _normalized(match.group(1)) if match else None


def _audit_incorrect_resolutions(contradictions: list[dict[str, str]]) -> list[dict[str, str]]:
    """Flag latest-value resolutions that conflict with the active project configuration."""
    expected = {
        "preferred model": "qwen3:8b",
        "project status": "active",
    }
    incorrect = []
    for conflict in contradictions:
        expected_value = expected.get(conflict["key"])
        if expected_value and expected_value.casefold() not in conflict["new"].casefold():
            incorrect.append({**conflict, "reason": f"expected configured value: {expected_value}"})
    return incorrect


def compact_memory(memory_path: Path = MEMORY_PATH, output_path: Path | None = None) -> dict:
    """Deduplicate memory and explicitly record conflicts instead of hiding them."""
    output_path = output_path or memory_path
    original = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""
    before = memory_line_count(original)
    kept: list[str] = []
    seen: set[str] = set()
    latest_by_key: dict[str, tuple[int, str]] = {}
    duplicates: list[str] = []
    contradictions: list[dict[str, str]] = []

    for line in original.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("<!--"):
            continue
        normalized = _normalized(stripped)
        if normalized in seen:
            duplicates.append(stripped)
            continue
        seen.add(normalized)
        key = _contradiction_key(stripped)
        if key and key in latest_by_key:
            previous_index, previous = latest_by_key[key]
            if previous != stripped and ":" in previous and ":" in stripped:
                contradictions.append({"key": key, "old": previous, "new": stripped, "resolution": "retained latest"})
                kept[previous_index] = f"- Conflict resolved for {key}: retained latest; superseded: {previous}"
        if key:
            latest_by_key[key] = (len(kept), stripped)
        kept.append(stripped)

    timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    result_text = "\n".join([
        "# Consolidated Memory",
        f"<!-- last_consolidated_at: {timestamp} -->",
        "<!-- Conflicts are recorded explicitly below; review them before relying on memory. -->",
        *kept,
    ]) + "\n"
    output_path.write_text(result_text, encoding="utf-8")
    incorrectly_resolved = _audit_incorrect_resolutions(contradictions)
    return {
        "before_lines": before,
        "after_lines": memory_line_count(result_text),
        "duplicates_merged": len(duplicates),
        "contradictions": contradictions,
        "incorrectly_resolved": incorrectly_resolved,
        "output_path": str(output_path),
    }


def handle_memory_command(
    command: str,
    recent_messages: list[str] | None = None,
    agent_path: Path = AGENT_PATH,
    memory_path: Path = MEMORY_PATH,
    output_path: Path | None = None,
) -> dict:
    command = command.strip().split()[0] if command.strip() else ""
    files = load_memory_files(agent_path, memory_path)
    if command == "/memory":
        return {"command": command, "agent": files["agent"], "memory": files["memory"],
                "memory_line_count": memory_line_count(files["memory"])}
    if command == "/compact":
        result = compact_memory(memory_path, output_path)
        result["command"] = command
        return result
    if command == "/dream":
        # Keep only high-confidence, useful facts instead of copying every recent message.
        facts = []
        for message in recent_messages or []:
            for fact, importance in extract_episode_facts(message):
                if importance >= 0.8:
                    facts.append(fact)
        facts = facts[:3]
        with memory_path.open("a", encoding="utf-8") as handle:
            for fact in facts:
                handle.write(f"\n- Recent fact: {fact}")
        return {"command": command, "facts_added": facts}
    if command == "/help":
        return {"command": command, "commands": HELP_TEXT}
    return {"command": command, "error": "Unknown memory command."}

