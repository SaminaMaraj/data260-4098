import argparse
import contextlib
import io
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parent.parent
CODE_DIR = REPO_ROOT / "code"
sys.path.insert(0, str(CODE_DIR))

from agents_graph import run_graph


REPORT_DIR = REPO_ROOT / "reports" / "hw02"
CASES_DIR = REPORT_DIR / "cases"
RAW_DIR = REPORT_DIR / "raw"
RUN_LOG_PATH = REPORT_DIR / "RUN_LOG.txt"

SCHEMA_INPUT_PATH = CASES_DIR / "schema_input.json"
ADVERSARIAL_INPUT_PATH = CASES_DIR / "adversarial_input.json"

SCHEMA_RUNS_PATH = RAW_DIR / "schema_runs.json"
CEILING_RUNS_PATH = RAW_DIR / "ceiling_runs.json"
ADVERSARIAL_RUNS_PATH = RAW_DIR / "adversarial_runs.json"
SUMMARY_PATH = RAW_DIR / "experiment_summary.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str) -> None:
    line = f"[{utc_now()}] {message}"
    print(line, flush=True)
    with RUN_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def load_results(path: Path, experiment: str) -> Dict[str, Any]:
    if path.exists():
        value = read_json(path)
        if not isinstance(value.get("runs"), list):
            raise ValueError(f"{path} does not contain a runs array")
        return value
    return {
        "experiment": experiment,
        "created_at_utc": utc_now(),
        "runs": [],
    }


def save_results(path: Path, value: Dict[str, Any]) -> None:
    value["updated_at_utc"] = utc_now()
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(value, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def classify(final_state: Dict[str, Any]) -> str:
    if final_state.get("status") != "completed":
        return "hit_turn_ceiling"

    turns = int(final_state.get("turn_count", 0))
    if turns == 1:
        return "valid_first_attempt"
    if turns == 2:
        return "valid_after_one_retry"
    return "valid_after_two_or_more_retries"


def execute_graph(
    case_data: Dict[str, Any],
    *,
    max_turns: int,
    model: str,
    base_url: str,
    temperature: float,
) -> Dict[str, Any]:
    arguments = SimpleNamespace(
        title=case_data["title"],
        content=case_data["content"],
        email=case_data["email"],
        strict=bool(case_data.get("strict", True)),
        model=model,
        base_url=base_url,
        temperature=temperature,
        max_turns=max_turns,
        force_review_issue=False,
    )

    hidden_console_output = io.StringIO()
    started = time.perf_counter()
    with contextlib.redirect_stdout(hidden_console_output):
        final_state = run_graph(arguments)
    latency_ms = round((time.perf_counter() - started) * 1000)

    return {
        "latency_ms": latency_ms,
        "status": final_state.get("status"),
        "turn_count": final_state.get("turn_count"),
        "classification": classify(final_state),
        "planner_proposal": final_state.get("planner_proposal", {}),
        "reviewer_feedback": final_state.get("reviewer_feedback", {}),
        "validation_error": final_state.get("validation_error", ""),
        "event_log": final_state.get("event_log", []),
    }


def run_batch(
    *,
    experiment: str,
    output_path: Path,
    case_path: Path,
    total_runs: int,
    max_turns: int,
    model: str,
    base_url: str,
    temperature: float,
) -> None:
    case_data = read_json(case_path)
    output = load_results(output_path, experiment)
    runs: List[Dict[str, Any]] = output["runs"]

    completed = {
        (str(item.get("experiment")), int(item.get("max_turns", 0)), int(item["run"]))
        for item in runs
    }

    output.update(
        {
            "case_path": str(case_path.relative_to(REPO_ROOT)),
            "model": model,
            "base_url": base_url,
            "temperature": temperature,
            "max_turns": max_turns,
            "expected_runs": total_runs,
        }
    )

    for run_number in range(1, total_runs + 1):
        run_key = (experiment, max_turns, run_number)
        if run_key in completed:
            log(
                f"Skipping completed experiment={experiment}, "
                f"ceiling={max_turns}, run={run_number}/{total_runs}"
            )
            continue

        started_at = utc_now()
        log(
            f"Starting experiment={experiment}, ceiling={max_turns}, "
            f"run={run_number}/{total_runs}"
        )

        try:
            result = execute_graph(
                case_data,
                max_turns=max_turns,
                model=model,
                base_url=base_url,
                temperature=temperature,
            )
        except Exception as exc:
            log(
                f"FAILED experiment={experiment}, ceiling={max_turns}, "
                f"run={run_number}/{total_runs}, error={type(exc).__name__}: {exc}"
            )
            save_results(output_path, output)
            raise

        record = {
            "experiment": experiment,
            "run": run_number,
            "max_turns": max_turns,
            "started_at_utc": started_at,
            "completed_at_utc": utc_now(),
            **result,
        }
        runs.append(record)
        save_results(output_path, output)

        log(
            f"Completed experiment={experiment}, ceiling={max_turns}, "
            f"run={run_number}/{total_runs}, status={record['status']}, "
            f"turns={record['turn_count']}, latency={record['latency_ms']} ms"
        )


def mean_latency(runs: List[Dict[str, Any]]) -> float:
    if not runs:
        return 0.0
    return round(statistics.mean(float(item["latency_ms"]) for item in runs), 2)


def create_summary() -> Dict[str, Any]:
    schema = load_results(SCHEMA_RUNS_PATH, "schema_validation")
    ceilings = load_results(CEILING_RUNS_PATH, "ceiling_comparison")
    adversarial = load_results(ADVERSARIAL_RUNS_PATH, "adversarial")

    schema_runs = schema["runs"]
    schema_counts = {
        category: sum(item.get("classification") == category for item in schema_runs)
        for category in (
            "valid_first_attempt",
            "valid_after_one_retry",
            "valid_after_two_or_more_retries",
            "hit_turn_ceiling",
        )
    }

    ceiling_summary: Dict[str, Any] = {}
    for ceiling in (2, 10):
        selected = [
            item for item in ceilings["runs"] if int(item.get("max_turns", 0)) == ceiling
        ]
        completed_count = sum(item.get("status") == "completed" for item in selected)
        ceiling_summary[str(ceiling)] = {
            "runs": len(selected),
            "completed": completed_count,
            "completion_rate_percent": (
                round((completed_count / len(selected)) * 100, 2) if selected else 0.0
            ),
            "mean_latency_ms": mean_latency(selected),
        }

    adversarial_runs = adversarial["runs"]
    adversarial_ceiling_count = sum(
        item.get("status") == "abandoned_at_ceiling" for item in adversarial_runs
    )

    summary = {
        "generated_at_utc": utc_now(),
        "schema_validation": {
            "runs": len(schema_runs),
            "outcome_counts": schema_counts,
            "mean_latency_ms": mean_latency(schema_runs),
        },
        "ceiling_comparison": ceiling_summary,
        "adversarial": {
            "runs": len(adversarial_runs),
            "hit_ceiling": adversarial_ceiling_count,
            "hit_ceiling_rate_percent": (
                round((adversarial_ceiling_count / len(adversarial_runs)) * 100, 2)
                if adversarial_runs
                else 0.0
            ),
            "mean_latency_ms": mean_latency(adversarial_runs),
        },
    }
    save_results(SUMMARY_PATH, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase",
        choices=("all", "schema", "ceilings", "adversarial", "summary"),
        default="all",
    )
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--temperature", type=float, default=0.7)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    for required_path in (SCHEMA_INPUT_PATH, ADVERSARIAL_INPUT_PATH):
        if not required_path.exists():
            raise FileNotFoundError(f"Required frozen input is missing: {required_path}")

    log(
        f"HW2 experiment runner started phase={args.phase}, model={args.model}, "
        f"temperature={args.temperature}"
    )

    if args.phase in {"all", "schema"}:
        run_batch(
            experiment="schema_validation",
            output_path=SCHEMA_RUNS_PATH,
            case_path=SCHEMA_INPUT_PATH,
            total_runs=30,
            max_turns=10,
            model=args.model,
            base_url=args.base_url,
            temperature=args.temperature,
        )

    if args.phase in {"all", "ceilings"}:
        for ceiling in (2, 10):
            run_batch(
                experiment="ceiling_comparison",
                output_path=CEILING_RUNS_PATH,
                case_path=SCHEMA_INPUT_PATH,
                total_runs=20,
                max_turns=ceiling,
                model=args.model,
                base_url=args.base_url,
                temperature=args.temperature,
            )

    if args.phase in {"all", "adversarial"}:
        run_batch(
            experiment="adversarial",
            output_path=ADVERSARIAL_RUNS_PATH,
            case_path=ADVERSARIAL_INPUT_PATH,
            total_runs=5,
            max_turns=2,
            model=args.model,
            base_url=args.base_url,
            temperature=args.temperature,
        )

    summary = create_summary()
    log(f"HW2 experiment runner finished phase={args.phase}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
