"""Demonstrate all three required retry outcomes without a database."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "mcp"))

from retry_utils import retry_call


class SequenceFailureInjector:
    def __init__(self, failures: list[bool]):
        self.failures = iter(failures)

    def __call__(self) -> None:
        if next(self.failures, False):
            raise RuntimeError("demo injected failure")


def main() -> None:
    first_success = retry_call(
        lambda: "success",
        fault_injector=SequenceFailureInjector([False]),
    )
    print("case=success_first_attempt", first_success)

    retry_success = retry_call(
        lambda: "success after retry",
        fault_injector=SequenceFailureInjector([True, False]),
    )
    print("case=failure_then_success", retry_success)

    all_failed = retry_call(
        lambda: "never returned",
        fault_injector=SequenceFailureInjector([True, True, True]),
    )
    print("case=failure_after_all_retries", all_failed)
    if all_failed.success:
        raise AssertionError("the final demo case should fail cleanly")


if __name__ == "__main__":
    main()
