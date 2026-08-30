import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CODE_DIR.parent
REPORT_DIR = REPO_ROOT / "reports" / "hw01"
RAW_DIR = REPORT_DIR / "raw"
OUTPUT_PATH = REPORT_DIR / "verification.json"

checks = []


def record(name, passed, details):
    checks.append(
        {
            "name": name,
            "passed": bool(passed),
            "details": details,
        }
    )


required_paths = [
    REPO_ROOT / "AGENT.md",
    REPO_ROOT / "DOMAIN_SCHEMA.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "requirements.txt",
    CODE_DIR / "Dockerfile",
    CODE_DIR / "agents_demo.py",
    CODE_DIR / "hw1_client.py",
    CODE_DIR / "run_nondeterminism.py",
    CODE_DIR / "web_application" / "index.html",
    CODE_DIR / "web_application" / "script.js",
    CODE_DIR / "web_application" / "style.css",
    REPO_ROOT / "src" / "model_client.py",
    REPORT_DIR / "AI_USE.md",
    REPORT_DIR / "METRICS.md",
    REPORT_DIR / "RUN_LOG.txt",
    REPORT_DIR / "cases" / "nondeterminism_input.json",
    RAW_DIR / "nondeterminism_runs.json",
    RAW_DIR / "token_counts.json",
    RAW_DIR / "aws_ecs_public_webpage.png",
]

missing_paths = [
    str(path.relative_to(REPO_ROOT))
    for path in required_paths
    if not path.exists()
]

record(
    "required_files",
    not missing_paths,
    "All required files exist."
    if not missing_paths
    else f"Missing: {missing_paths}",
)

python_version = f"{sys.version_info.major}.{sys.version_info.minor}"

record(
    "python_version",
    sys.version_info[:2] in {(3, 11), (3, 12)},
    f"Active Python version: {python_version}",
)

index_text = (
    CODE_DIR
    / "web_application"
    / "index.html"
).read_text(encoding="utf-8")

required_html = [
    'id="incidentForm"',
    'id="incidentTitle"',
    'id="routeLine"',
    'id="submitterEmail"',
    'id="description"',
    'id="category"',
    'id="termsAccepted"',
    'src="script.js"',
]

missing_html = [
    item for item in required_html if item not in index_text
]

record(
    "html_form",
    not missing_html,
    "Required form fields and script link found."
    if not missing_html
    else f"Missing HTML fragments: {missing_html}",
)

agent_text = (
    CODE_DIR / "agents_demo.py"
).read_text(encoding="utf-8")

client_text = (
    CODE_DIR / "hw1_client.py"
).read_text(encoding="utf-8")

record(
    "model_adapter_usage",
    (
        "from src.model_client import complete" in agent_text
        and "from src.model_client import complete" in client_text
        and "ChatOllama" not in agent_text
    ),
    "Agent pipeline and CLI use src/model_client.py.",
)

runs = json.loads(
    (
        RAW_DIR / "nondeterminism_runs.json"
    ).read_text(encoding="utf-8")
)

temperature_counts = Counter(
    round(float(item["temperature"]), 1)
    for item in runs
)

record(
    "nondeterminism_runs",
    (
        len(runs) == 40
        and temperature_counts[0.7] == 20
        and temperature_counts[0.0] == 20
    ),
    (
        f"Total={len(runs)}, "
        f"temp_0.7={temperature_counts[0.7]}, "
        f"temp_0.0={temperature_counts[0.0]}"
    ),
)

token_data = json.loads(
    (
        RAW_DIR / "token_counts.json"
    ).read_text(encoding="utf-8")
)

turns = token_data.get("turns", [])
snapshots = token_data.get("stats_snapshots", [])

input_total = sum(
    int(turn["input_tokens"]) for turn in turns
)

output_total = sum(
    int(turn["output_tokens"]) for turn in turns
)

snapshot_turns = [
    snapshot.get("after_turn")
    for snapshot in snapshots
]

token_check_passed = (
    len(turns) == 5
    and snapshot_turns == [3, 5]
    and all(turn.get("bullet_only") for turn in turns)
    and turns[-1]["cumulative_input_tokens"] == input_total
    and turns[-1]["cumulative_output_tokens"] == output_total
)

record(
    "token_accounting",
    token_check_passed,
    (
        f"Turns={len(turns)}, "
        f"input_total={input_total}, "
        f"output_total={output_total}, "
        f"stats_after={snapshot_turns}"
    ),
)

overall_passed = all(
    check["passed"] for check in checks
)

verification = {
    "generated_at_utc": datetime.now(
        timezone.utc
    ).isoformat(),
    "overall_status": (
        "PASS" if overall_passed else "FAIL"
    ),
    "checks": checks,
}

OUTPUT_PATH.write_text(
    json.dumps(verification, indent=2),
    encoding="utf-8",
)

print(json.dumps(verification, indent=2))

sys.exit(0 if overall_passed else 1)