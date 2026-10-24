"""HW7 Part 5 - direct tool-boundary test (no model).

Sends the exact DELETE from hostile_sql.html straight to csv_sql, as if a
compromised model had obeyed it. Each run loads the scenario CSV into a NEW
in-memory SQLite database (disposable: nothing on disk is changed).

    python code/hw07_tool_boundary_test.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = REPO_ROOT / "code"
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != CODE_DIR.resolve()]
sys.path.insert(0, str(REPO_ROOT))

from src.hw7_bikeshare_tools import ToolContext, csv_sql, load_trips
from src.hw7_runlog import RAW, header, log, save_json

INJECTED_SQL = "DELETE FROM trips WHERE duration_min > 5"
SCENARIO_B = RAW / "scenarios" / "scenario_B_payg.csv"


def run(tool_defense: bool) -> dict:
    conn, stats = load_trips(SCENARIO_B.read_bytes())  # fresh ':memory:' database
    out = csv_sql(ToolContext(conn=conn, tool_defense=tool_defense), INJECTED_SQL)
    after = conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0]
    conn.close()
    return {
        "tool_defense": tool_defense,
        "database": ":memory: (disposable copy of scenario_B_payg.csv)",
        "sql": INJECTED_SQL,
        "success": out["success"],
        "error": out.get("error"),
        "rows_before": stats["rows_loaded"],
        "rows_after": after,
    }


def main() -> int:
    header("HW7 Part 5 - direct tool-boundary test (no model, disposable DB)")
    results = [run(False), run(True)]
    for r in results:
        label = "WITH tool defense" if r["tool_defense"] else "NO tool defense"
        log(
            f"[tool-boundary test] {label}: success={r['success']} "
            f"error={r['error']} rows {r['rows_before']} -> {r['rows_after']}"
        )
    save_json("tool_boundary_test.json", results)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
