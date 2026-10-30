"""HW8 Part 2 Planner: s4098_inbox (question) -> s4098_tasks (plan).

    python planner.py        (from code/hw8, or: python code/hw8/planner.py)

Run with --help for the Part 3 options (commit mode, poison policy, ...).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.hw8_kafka.agent_runtime import Agent, agent_args  # noqa: E402
from src.hw8_kafka.agents import plan  # noqa: E402
from src.hw8_kafka.config import INBOX_TOPIC, PLANNER_GROUP, TASKS_TOPIC  # noqa: E402

if __name__ == "__main__":
    args = agent_args("PLANNER", PLANNER_GROUP)
    agent = Agent(
        name="PLANNER",
        in_topic=INBOX_TOPIC,
        out_topic=TASKS_TOPIC,
        handler=plan,
        args=args,
    )
    asyncio.run(agent.run())
