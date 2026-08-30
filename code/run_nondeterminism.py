import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CODE_DIR.parent

INPUT_PATH = (
    REPO_ROOT
    / "reports"
    / "hw01"
    / "cases"
    / "nondeterminism_input.json"
)

OUTPUT_PATH = (
    REPO_ROOT
    / "reports"
    / "hw01"
    / "raw"
    / "nondeterminism_runs.json"
)


def save_results(results):
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(results, indent=2),
        encoding="utf-8",
    )


def main():
    case_data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))

    if OUTPUT_PATH.exists():
        results = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    else:
        results = []

    completed_runs = {
        (float(item["temperature"]), int(item["run"]))
        for item in results
    }

    temperatures = [0.7, 0.0]

    for temperature in temperatures:
        for run_number in range(1, 21):
            run_key = (temperature, run_number)

            if run_key in completed_runs:
                print(
                    f"Skipping completed run: "
                    f"temperature={temperature}, run={run_number}",
                    flush=True,
                )
                continue

            command = [
                sys.executable,
                str(CODE_DIR / "agents_demo.py"),
                "--model",
                "qwen3:8b",
                "--title",
                case_data["title"],
                "--content",
                case_data["content"],
                "--email",
                case_data["email"],
                "--temperature",
                str(temperature),
                "--strict",
            ]

            print(
                f"Starting temperature={temperature}, "
                f"run={run_number}/20",
                flush=True,
            )

            start_time = time.perf_counter()

            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
            )

            latency_ms = round(
                (time.perf_counter() - start_time) * 1000
            )

            if completed.returncode != 0:
                print(completed.stderr, file=sys.stderr)
                print(
                    "The experiment stopped, but completed runs "
                    "remain saved. Run this script again to resume.",
                    file=sys.stderr,
                )
                sys.exit(completed.returncode)

            marker = "Publish Package"

            if marker not in completed.stdout:
                print(completed.stdout, file=sys.stderr)
                raise RuntimeError(
                    "Publish Package was not found in the output."
                )

            publish_text = completed.stdout.rsplit(marker, 1)[1].strip()
            publish_package = json.loads(publish_text)
            final_data = publish_package["agents"]["final"]

            result = {
                "temperature": temperature,
                "run": run_number,
                "tags": final_data["tags"],
                "summary": final_data["summary"],
                "latency_ms": latency_ms,
                "timestamp_utc": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

            results.append(result)
            save_results(results)

            print(
                f"Completed temperature={temperature}, "
                f"run={run_number}/20, latency={latency_ms} ms",
                flush=True,
            )

    print(
        f"All {len(results)} runs are saved in {OUTPUT_PATH}",
        flush=True,
    )


if __name__ == "__main__":
    main()