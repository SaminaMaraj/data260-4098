"""Shim so scripts in code/mcp can use the shared RUN_LOG helper in src/."""

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.append(_ROOT)

from src.hw7_runlog import HW07, RAW, RUN_LOG, header, log, save_json  # noqa: E402

__all__ = ["HW07", "RAW", "RUN_LOG", "header", "log", "save_json"]
