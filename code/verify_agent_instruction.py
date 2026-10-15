"""Verify that the file-memory prompt function follows AGENT.md rules."""

from __future__ import annotations

import inspect
from pathlib import Path

from src.file_memory import build_memory_system_prompt


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    instructions = (ROOT / "AGENT.md").read_text(encoding="utf-8")
    function_source = inspect.getsource(build_memory_system_prompt)
    prompt = build_memory_system_prompt("Use FastAPI.", "Remember VTA Route 22.")
    checks = {
        "agent_has_project_instruction": "Project description" in instructions,
        "agent_has_stack_instruction": "Technology stack" in instructions,
        "agent_has_testing_instruction": "Testing approach" in instructions,
        "function_is_typed": "-> str" in function_source,
        "function_includes_agent_and_memory": "Durable agent instructions" in prompt and "Durable user/project memory" in prompt,
        "function_does_not_expose_secret": "api_key" not in prompt.casefold(),
    }
    result = {"checks": checks, "passed": all(checks.values())}
    print(result)
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
