"""Tiny tee logger: prints a line and appends it, timestamped, to RUN_LOG.txt."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HW07 = REPO_ROOT / "reports" / "hw07"
RAW = HW07 / "raw"
RUN_LOG = HW07 / "RUN_LOG.txt"
STUDENT = "Kazi Samina Maraj Mumu"


def commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def log(line: str = "") -> None:
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    print(line, flush=True)
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {line}\n")


def header(title: str) -> None:
    log("=" * 78)
    log(f"{STUDENT} | {title}")
    log(
        f"commit={commit_hash()} model={os.environ.get('SMOL_MODEL', 'qwen3:8b')} "
        f"host={platform.node()} python={platform.python_version()}"
    )
    log("=" * 78)


def save_json(name: str, data) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / name
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")
    return path
