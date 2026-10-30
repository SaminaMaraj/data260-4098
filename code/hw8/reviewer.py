"""HW8 Part 2 Reviewer: s4098_drafts (draft) -> s4098_final (approval).

    python reviewer.py       (from code/hw8, or: python code/hw8/reviewer.py)

Run with --help for the Part 3 options (commit mode, poison policy, ...).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.hw8_kafka.agent_runtime import Agent, agent_args  # noqa: E402
from src.hw8_kafka.agents import review  # noqa: E402
from src.hw8_kafka.config import DRAFTS_TOPIC, FINAL_TOPIC, REVIEWER_GROUP  # noqa: E402

if __name__ == "__main__":
    args = agent_args("REVIEWER", REVIEWER_GROUP)
    agent = Agent(
        name="REVIEWER",
        in_topic=DRAFTS_TOPIC,
        out_topic=FINAL_TOPIC,
        handler=review,
        args=args,
    )
    asyncio.run(agent.run())
