import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import URLError
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "reports" / "hw02"
RAW_DIR = REPORT_DIR / "raw"
OUTPUT_PATH = REPORT_DIR / "verification.json"

SID4 = 4098
PORT_BASE = 8498
SEED = 4098
VERIFY_SEED = 264098
MODEL = "qwen3:8b"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def add_check(
    checks: List[Dict[str, Any]],
    name: str,
    passed: bool,
    details: str,
) -> None:
    checks.append({"name": name, "passed": bool(passed), "details": details})


def current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def fetch_health() -> Dict[str, Any]:
    with urlopen(f"http://127.0.0.1:{PORT_BASE}/health", timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def check_fastapi_port() -> Dict[str, Any]:
    server_process = None
    try:
        try:
            health = fetch_health()
        except (URLError, TimeoutError, ConnectionError):
            server_process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "src.api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(PORT_BASE),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            deadline = time.monotonic() + 20
            health = None
            while time.monotonic() < deadline:
                try:
                    health = fetch_health()
                    break
                except (URLError, TimeoutError, ConnectionError):
                    time.sleep(0.5)

            if health is None:
                raise RuntimeError("FastAPI did not become ready within 20 seconds")

        if health.get("status") != "ok":
            raise ValueError(f"Unexpected health response: {health}")
        if int(health.get("port", -1)) != PORT_BASE:
            raise ValueError(f"Health response did not report port {PORT_BASE}: {health}")
        return health
    finally:
        if server_process is not None:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()
                server_process.wait(timeout=5)


def parse_final_graph_result(output: str) -> Dict[str, Any]:
    marker = "--- FINAL GRAPH RESULT ---"
    if marker not in output:
        raise ValueError("Graph output did not contain the final-result marker")
    result_text = output.rsplit(marker, 1)[1].strip()
    value = json.loads(result_text)
    if not isinstance(value, dict):
        raise ValueError("Final graph result was not a JSON object")
    return value


def check_graph_smoke(timeout_seconds: int) -> Dict[str, Any]:
    case = read_json(REPORT_DIR / "cases" / "schema_input.json")
    command = [
        sys.executable,
        "code/agents_graph.py",
        "--title",
        case["title"],
        "--content",
        case["content"],
        "--email",
        case["email"],
        "--model",
        MODEL,
        "--temperature",
        "0.0",
        "--max-turns",
        "2",
        "--strict",
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Graph process exited with {completed.returncode}: {completed.stderr[-500:]}"
        )

    final = parse_final_graph_result(completed.stdout)
    if final.get("status") not in {"completed", "abandoned_at_ceiling"}:
        raise ValueError(f"Unexpected graph status: {final.get('status')}")

    proposal = final.get("planner_proposal", {})
    tags = proposal.get("tags", [])
    summary = str(proposal.get("summary", ""))
    if len(tags) != 3:
        raise ValueError(f"Graph returned {len(tags)} tags instead of 3")
    if any(not isinstance(tag, str) or not 3 <= len(tag) <= 30 for tag in tags):
        raise ValueError(f"Graph returned an invalid tag: {tags}")
    if len(summary.split()) > 25:
        raise ValueError("Graph summary exceeded 25 words")

    return {
        "status": final["status"],
        "turn_count": final.get("turn_count"),
        "tag_count": len(tags),
        "summary_word_count": len(summary.split()),
    }


def check_experiment_files() -> Dict[str, Any]:
    schema = read_json(RAW_DIR / "schema_runs.json")["runs"]
    ceilings = read_json(RAW_DIR / "ceiling_runs.json")["runs"]
    adversarial = read_json(RAW_DIR / "adversarial_runs.json")["runs"]

    if len(schema) != 30:
        raise ValueError(f"Expected 30 schema runs, found {len(schema)}")
    if len(ceilings) != 40:
        raise ValueError(f"Expected 40 ceiling runs, found {len(ceilings)}")
    if len(adversarial) != 5:
        raise ValueError(f"Expected 5 adversarial runs, found {len(adversarial)}")

    ceiling_2 = sum(int(run.get("max_turns", 0)) == 2 for run in ceilings)
    ceiling_10 = sum(int(run.get("max_turns", 0)) == 10 for run in ceilings)
    if ceiling_2 != 20 or ceiling_10 != 20:
        raise ValueError(
            f"Ceiling split must be 20/20, found ceiling2={ceiling_2}, "
            f"ceiling10={ceiling_10}"
        )

    return {
        "schema_runs": len(schema),
        "ceiling_2_runs": ceiling_2,
        "ceiling_10_runs": ceiling_10,
        "adversarial_runs": len(adversarial),
    }


def check_saved_schema_outputs() -> Dict[str, Any]:
    runs = read_json(RAW_DIR / "schema_runs.json")["runs"]
    invalid: List[str] = []

    for run in runs:
        proposal = run.get("planner_proposal", {})
        tags = proposal.get("tags", [])
        summary = str(proposal.get("summary", ""))
        run_number = run.get("run")

        if len(tags) != 3:
            invalid.append(f"run {run_number}: tag count {len(tags)}")
            continue
        if len({str(tag).casefold() for tag in tags}) != 3:
            invalid.append(f"run {run_number}: duplicate tags")
        if any(not isinstance(tag, str) or not 3 <= len(tag) <= 30 for tag in tags):
            invalid.append(f"run {run_number}: tag length/type violation")
        if not summary or len(summary.split()) > 25:
            invalid.append(f"run {run_number}: summary violation")

    if invalid:
        raise ValueError("; ".join(invalid[:10]))

    return {
        "validated_runs": len(runs),
        "invalid_runs": 0,
        "required_tags_per_run": 3,
        "maximum_summary_words": 25,
    }


def check_adapter_usage() -> Dict[str, Any]:
    graph_source = (REPO_ROOT / "code" / "agents_graph.py").read_text(encoding="utf-8")
    required_import = "from src.model_client import complete"
    if required_import not in graph_source:
        raise ValueError("agents_graph.py does not import complete from src.model_client")
    return {"adapter_import_found": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-timeout", type=int, default=300)
    parser.add_argument(
        "--skip-model",
        action="store_true",
        help="Skip only the live LangGraph model smoke test.",
    )
    args = parser.parse_args()

    checks: List[Dict[str, Any]] = []
    required_files = [
        REPO_ROOT / "code" / "agents_graph.py",
        REPO_ROOT / "code" / "run_hw2_experiments.py",
        REPO_ROOT / "src" / "api.py",
        REPO_ROOT / "src" / "model_client.py",
        REPORT_DIR / "cases" / "schema_input.json",
        REPORT_DIR / "cases" / "adversarial_input.json",
        RAW_DIR / "schema_runs.json",
        RAW_DIR / "ceiling_runs.json",
        RAW_DIR / "adversarial_runs.json",
        RAW_DIR / "experiment_summary.json",
        REPORT_DIR / "METRICS.md",
        REPORT_DIR / "AI_USE.md",
        REPORT_DIR / "RUN_LOG.txt",
    ]
    missing = [str(path.relative_to(REPO_ROOT)) for path in required_files if not path.exists()]
    add_check(
        checks,
        "required_files",
        not missing,
        "All required implementation and experiment files exist."
        if not missing
        else f"Missing: {missing}",
    )

    python_ok = sys.version_info[:2] == (3, 12)
    add_check(
        checks,
        "python_version",
        python_ok,
        f"Active Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )

    try:
        health = check_fastapi_port()
        add_check(checks, "fastapi_port", True, json.dumps(health, sort_keys=True))
    except Exception as exc:
        add_check(checks, "fastapi_port", False, f"{type(exc).__name__}: {exc}")

    try:
        counts = check_experiment_files()
        add_check(checks, "experiment_counts", True, json.dumps(counts, sort_keys=True))
    except Exception as exc:
        add_check(checks, "experiment_counts", False, f"{type(exc).__name__}: {exc}")

    try:
        schema_details = check_saved_schema_outputs()
        add_check(checks, "saved_schema_outputs", True, json.dumps(schema_details, sort_keys=True))
    except Exception as exc:
        add_check(checks, "saved_schema_outputs", False, f"{type(exc).__name__}: {exc}")

    try:
        adapter_details = check_adapter_usage()
        add_check(checks, "model_adapter_usage", True, json.dumps(adapter_details, sort_keys=True))
    except Exception as exc:
        add_check(checks, "model_adapter_usage", False, f"{type(exc).__name__}: {exc}")

    if args.skip_model:
        add_check(checks, "langgraph_smoke", True, "Skipped by --skip-model.")
    else:
        try:
            graph_details = check_graph_smoke(args.model_timeout)
            add_check(checks, "langgraph_smoke", True, json.dumps(graph_details, sort_keys=True))
        except Exception as exc:
            add_check(checks, "langgraph_smoke", False, f"{type(exc).__name__}: {exc}")

    verification = {
        "homework": 2,
        "generated_at_utc": utc_now(),
        "sid4": SID4,
        "port_base": PORT_BASE,
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "tested_commit": current_commit(),
        "model_configuration": {
            "model": MODEL,
            "experiment_temperature": 0.7,
            "graph_smoke_temperature": 0.0,
            "graph_smoke_ceiling": 2,
        },
        "overall_status": "PASS" if all(check["passed"] for check in checks) else "FAIL",
        "checks": checks,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(verification, indent=2))

    if verification["overall_status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
