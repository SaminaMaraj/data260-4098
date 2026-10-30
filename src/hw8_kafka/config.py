"""HW8 personal configuration, topic names and the shared log helper.

Every HW8 process (worker, API wrapper, agents, test runners) imports its
topic names from here, so the PREFIX is defined in exactly one place.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

STUDENT_NAME = "Kazi Samina Maraj Mumu"

SID4 = 4098
PORT_BASE = 8000 + (SID4 % 900)  # 8498
PREFIX = f"s{SID4}"  # s4098
SEED = SID4  # 4098
VERIFY_SEED = 260000 + SID4  # 264098
DOMAIN_ID = SID4 % 8  # 2 -> municipal transit incidents

KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")

# Part 1 - request/response service (primary entity: Incident)
REQUEST_TOPIC = f"{PREFIX}_entity_requests"
RESPONSE_TOPIC = f"{PREFIX}_entity_responses"

# Part 2 - three-agent pipeline
INBOX_TOPIC = f"{PREFIX}_inbox"
TASKS_TOPIC = f"{PREFIX}_tasks"
DRAFTS_TOPIC = f"{PREFIX}_drafts"
FINAL_TOPIC = f"{PREFIX}_final"

# Part 3 - dead-letter topic for poison messages
DEAD_LETTER_TOPIC = f"{PREFIX}_dead_letter"

# topic -> number of partitions (replication factor is 1 on a single broker)
TOPICS: dict[str, int] = {
    REQUEST_TOPIC: 1,
    RESPONSE_TOPIC: 1,
    INBOX_TOPIC: 1,
    TASKS_TOPIC: 2,  # two partitions, required for the ordering test
    DRAFTS_TOPIC: 1,
    FINAL_TOPIC: 1,
    DEAD_LETTER_TOPIC: 1,
}

# consumer groups
WORKER_GROUP = f"{PREFIX}_incident_worker"
PLANNER_GROUP = f"{PREFIX}_planners"
WRITER_GROUP = f"{PREFIX}_writers"
REVIEWER_GROUP = f"{PREFIX}_reviewers"


def now_iso() -> str:
    """UTC timestamp with milliseconds, used in every log line."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def log(component: str, message: str) -> None:
    """One log line: '<utc time> [COMPONENT] message' (flushed immediately)."""
    print(f"{now_iso()} [{component}] {message}", flush=True)


def banner(script: str) -> None:
    """Name + config at the top of every terminal, for the screenshots."""
    print(
        f"{STUDENT_NAME} | {script} | PREFIX={PREFIX} PORT_BASE={PORT_BASE} "
        f"KAFKA={KAFKA_BOOTSTRAP}",
        flush=True,
    )
