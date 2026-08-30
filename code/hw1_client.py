import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.model_client import complete


AGENT_PATH = REPO_ROOT / "AGENT.md"
TOKEN_LOG_PATH = (
    REPO_ROOT
    / "reports"
    / "hw01"
    / "raw"
    / "token_counts.json"
)


def history_length(messages):
    return len(json.dumps(messages, ensure_ascii=False))


def save_token_log(token_log):
    TOKEN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_LOG_PATH.write_text(
        json.dumps(token_log, indent=2),
        encoding="utf-8",
    )


def main():
    system_prompt = AGENT_PATH.read_text(encoding="utf-8")

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    turn_count = 0
    cumulative_input_tokens = 0
    cumulative_output_tokens = 0

    token_log = {
        "turns": [],
        "stats_snapshots": [],
    }

    print("Code Review Client")
    print("Enter code or a review request.")
    print("Commands: /stats and /exit")

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        if user_input.lower() in {"/exit", "/quit"}:
            break

        if user_input.lower() == "/stats":
            snapshot = {
                "after_turn": turn_count,
                "turn_count": turn_count,
                "cumulative_input_tokens": cumulative_input_tokens,
                "cumulative_output_tokens": cumulative_output_tokens,
                "history_length": history_length(messages),
            }

            token_log["stats_snapshots"].append(snapshot)
            save_token_log(token_log)

            print(
                "Stats: "
                f"turns={turn_count}, "
                f"cumulative_input_tokens="
                f"{cumulative_input_tokens}, "
                f"cumulative_output_tokens="
                f"{cumulative_output_tokens}, "
                f"history_length="
                f"{snapshot['history_length']}"
            )
            continue

        messages.append(
            {
                "role": "user",
                "content": user_input,
            }
        )

        result = complete(messages)
        assistant_text = result["content"].strip()

        messages.append(
            {
                "role": "assistant",
                "content": assistant_text,
            }
        )

        turn_count += 1
        cumulative_input_tokens += result["input_tokens"]
        cumulative_output_tokens += result["output_tokens"]

        response_lines = [
            line
            for line in assistant_text.splitlines()
            if line.strip()
        ]

        bullet_only = bool(response_lines) and all(
            line.startswith("- ")
            for line in response_lines
        )

        turn_record = {
            "turn": turn_count,
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
            "total_tokens": result["total_tokens"],
            "cumulative_input_tokens": cumulative_input_tokens,
            "cumulative_output_tokens": cumulative_output_tokens,
            "history_length": history_length(messages),
            "bullet_only": bullet_only,
        }

        token_log["turns"].append(turn_record)
        save_token_log(token_log)

        print(f"\nAssistant:\n{assistant_text}")
        print(
            "Bullet-only format followed: "
            f"{'YES' if bullet_only else 'NO'}"
        )
        print(
            "Turn tokens: "
            f"input={result['input_tokens']}, "
            f"output={result['output_tokens']}, "
            f"total={result['total_tokens']}"
        )

    save_token_log(token_log)

    print("\nCumulative statistics")
    print(f"Turns: {turn_count}")
    print(
        f"Cumulative input tokens: "
        f"{cumulative_input_tokens}"
    )
    print(
        f"Cumulative output tokens: "
        f"{cumulative_output_tokens}"
    )


if __name__ == "__main__":
    main()