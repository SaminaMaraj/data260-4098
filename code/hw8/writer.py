"""HW8 Part 2 Writer: s4098_tasks (plan) -> s4098_drafts (draft answer).

    python writer.py         (from code/hw8, or: python code/hw8/writer.py)

Run with --help for the Part 3 options (commit mode, poison policy, ...).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.hw8_kafka.agent_runtime import Agent, agent_args  # noqa: E402
from src.hw8_kafka.agents import write  # noqa: E402
from src.hw8_kafka.config import DRAFTS_TOPIC, TASKS_TOPIC, WRITER_GROUP  # noqa: E402

if __name__ == "__main__":
    args = agent_args("WRITER", WRITER_GROUP)
    agent = Agent(
        name="WRITER",
        in_topic=TASKS_TOPIC,
        out_topic=DRAFTS_TOPIC,
        handler=write,
        args=args,
    )
    asyncio.run(agent.run())
