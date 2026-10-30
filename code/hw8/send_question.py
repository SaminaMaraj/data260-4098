"""HW8 Part 2: put one question on s4098_inbox and wait for it on s4098_final.

    python send_question.py
    python send_question.py --question "..."

The correlation_id is created here once; the final message must carry the
same value. The journey (every topic/partition/offset with timestamps) is
printed from the trace the agents attach, and saved to reports/hw08/raw/.
"""

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.hw8_kafka.config import (  # noqa: E402
    FINAL_TOPIC,
    INBOX_TOPIC,
    banner,
    log,
    now_iso,
)
from src.hw8_kafka.topics import (  # noqa: E402
    encode,
    ensure_topics,
    make_producer,
    tail_consumer,
)

C = "SENDER"
DEFAULT_QUESTION = (
    "A light-rail train lost power and stopped between two stations during the evening "
    "rush. What should the transit agency do in the first 30 minutes?"
)


async def main(args) -> int:
    banner("send_question.py (Part 2)")
    await ensure_topics(C)
    final = await tail_consumer(FINAL_TOPIC)  # listen before sending
    producer = await make_producer()
    cid = str(uuid.uuid4())
    message = {
        "correlation_id": cid,
        "question": args.question,
        "sent_at": now_iso(),
        "sender": "send_question.py",
    }
    if args.experiment:
        message["experiment"] = args.experiment
    meta = await producer.send_and_wait(INBOX_TOPIC, encode(message), key=cid.encode())
    log(
        C,
        f"SEND to {meta.topic} partition={meta.partition} offset={meta.offset} "
        f"correlation_id={cid}",
    )
    log(C, f"SEND message={json.dumps(message)}")
    await producer.stop()
    if args.no_wait:
        await final.stop()
        return 0

    log(
        C,
        f"waiting on {FINAL_TOPIC} for correlation_id={cid} (timeout {args.timeout}s)",
    )
    result = None
    try:
        async with asyncio.timeout(args.timeout):
            async for msg in final:
                value = json.loads(msg.value.decode())
                if value.get("correlation_id") == cid:
                    log(
                        C,
                        f"RECEIVE from {msg.topic} partition={msg.partition} "
                        f"offset={msg.offset} correlation_id={cid}",
                    )
                    result = value
                    break
    except TimeoutError:
        log(C, "TIMEOUT - is every agent running?")
    finally:
        await final.stop()
    if result is None:
        return 1

    print("\n=== Message journey (from the trace each agent appended) ===")
    print(f"{message['sent_at']} [SENDER] -> {INBOX_TOPIC} correlation_id={cid}")
    for hop in result.get("trace", []):
        print(
            f"{hop['received_at']} [{hop['agent']}:{hop['instance']}] <- "
            f"{hop['in_topic']}"
            f"[{hop['partition']}] offset={hop['offset']} ... sent {hop['sent_at']}"
        )
    print(f"{now_iso()} [SENDER] <- {FINAL_TOPIC} status={result.get('status')}")
    print(
        "correlation_id preserved through every stage: "
        f"{result.get('correlation_id') == cid}"
    )

    final_json = {k: v for k, v in result.items() if k != "trace"}
    print("\n=== Final JSON on s4098_final ===")
    print(json.dumps(final_json, indent=2, ensure_ascii=False))

    if not args.experiment:
        raw = ROOT / "reports" / "hw08" / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        (raw / "part2_final.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False)
        )
        log(C, f"saved {raw / 'part2_final.json'}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    parser.add_argument("--experiment", default=None)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--no-wait", action="store_true")
    raise SystemExit(asyncio.run(main(parser.parse_args())))
