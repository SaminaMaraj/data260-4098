"""Small retry and deterministic fault-injection utilities for HW5."""

from __future__ import annotations

import random
import signal
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable


MAX_RETRIES = 2
BASE_DELAY_SECONDS = 0.05
MAX_DELAY_SECONDS = 0.20
DEFAULT_TIMEOUT_SECONDS = 2.0
VERIFY_SEED = 264098


class InjectedFailure(RuntimeError):
    """Raised only when the controlled fault injector chooses a failure."""


class AttemptTimeout(TimeoutError):
    """Raised when one operation exceeds its per-attempt timeout."""


@dataclass
class RetryResult:
    success: bool
    value: Any = None
    error: str | None = None
    attempts: int = 0
    latency_ms: float = 0.0


def _alarm_handler(signum: int, frame: Any) -> None:
    del signum, frame
    raise AttemptTimeout("operation exceeded per-attempt timeout")


def _run_with_timeout(
    operation: Callable[[], Any],
    timeout_seconds: float,
) -> Any:
    """Run one synchronous operation with a Unix per-attempt timeout."""
    if threading.current_thread() is not threading.main_thread():
        started = time.perf_counter()
        value = operation()
        if time.perf_counter() - started > timeout_seconds:
            raise AttemptTimeout("operation exceeded per-attempt timeout")
        return value

    previous_handler = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return operation()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def retry_call(
    operation: Callable[[], Any],
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_retries: int = MAX_RETRIES,
    base_delay_seconds: float = BASE_DELAY_SECONDS,
    max_delay_seconds: float = MAX_DELAY_SECONDS,
    fault_injector: Callable[[], None] | None = None,
) -> RetryResult:
    """Try an operation with timeout and bounded exponential backoff.

    max_retries counts retries after the first attempt, so the default allows
    three total attempts. The fault injector runs once per attempt.
    """
    started = time.perf_counter()
    last_error: Exception | None = None
    total_attempts = max_retries + 1

    for attempt in range(1, total_attempts + 1):
        try:
            if fault_injector is not None:
                fault_injector()
            value = _run_with_timeout(operation, timeout_seconds)
            return RetryResult(
                success=True,
                value=value,
                attempts=attempt,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:  # one clean result for every failed call
            last_error = exc
            if attempt == total_attempts:
                break
            delay = min(
                base_delay_seconds * (2 ** (attempt - 1)),
                max_delay_seconds,
            )
            time.sleep(delay)

    return RetryResult(
        success=False,
        error=str(last_error) if last_error else "operation failed",
        attempts=total_attempts,
        latency_ms=(time.perf_counter() - started) * 1000,
    )


class SeededFaultInjector:
    """Produce a repeatable failure sequence for a selected failure rate."""

    def __init__(self, failure_rate: float, seed: int = VERIFY_SEED):
        if not 0.0 <= failure_rate <= 1.0:
            raise ValueError("failure_rate must be between 0.0 and 1.0")
        self.failure_rate = failure_rate
        self.rng = random.Random(seed)

    def __call__(self) -> None:
        if self.rng.random() < self.failure_rate:
            raise InjectedFailure(
                f"seeded injected failure at rate {self.failure_rate:.0%}"
            )
