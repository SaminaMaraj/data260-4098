"""Offline tests for the HW7 Part 4-6 tools (no model, no network, no DB).

python tests/test_hw07_tools.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.hw7_bikeshare_tools import (  # noqa: E402
    ToolContext,
    calculator,
    csv_sql,
    load_trips,
    policy_retriever,
)
from src.hw7_file_tools import FileTools, confirm_bash, is_destructive  # noqa: E402

CSV = (
    "ride_id,rideable_type,started_at,ended_at,start_station_name,"
    "end_station_name,member_casual,rider_id\n"
    "R1,classic_bike,2025-09-01 08:00:00.000,2025-09-01 08:10:30.000,A,B,casual,r1\n"
    "R2,electric_bike,2025-09-02 09:00:00,2025-09-02 09:20:00,B,C,member,r1\n"
    "R3,classic_bike,2025-09-09 10:00:00,2025-09-09 09:00:00,C,D,member,r2\n"
).encode()
FIXTURE = REPO_ROOT / "reports" / "hw07" / "fixtures" / "hostile_sql.html"


def ctx(**flags) -> ToolContext:
    conn, _stats = load_trips(CSV)
    return ToolContext(conn=conn, **flags)


def test_load_trips_derives_columns_and_drops_bad_rows():
    conn, stats = load_trips(CSV)
    assert stats["rows_loaded"] == 2 and stats["dropped_nonpositive_or_over_24h"] == 1
    row = conn.execute("SELECT duration_min, week_start FROM trips WHERE ride_id='R1'")
    assert row.fetchone() == (11, "2025-09-01")


def test_csv_sql_select_shape():
    out = csv_sql(ctx(), "SELECT COUNT(*) AS n FROM trips")
    assert out["success"] and out["data"] == {
        "rows": [{"n": 2}],
        "row_count": 1,
        "source": "uploaded.csv",
    }
    assert out["source"] == "uploaded.csv" and "ts" in out


def test_csv_sql_blocks_non_select_and_stacked():
    c = ctx()
    for sql in [
        "DELETE FROM trips",
        "SELECT 1; DROP TABLE trips",
        "UPDATE trips SET duration_min = 0",
        "ATTACH DATABASE 'x.db' AS x",
        "PRAGMA writable_schema = 1",
    ]:
        out = csv_sql(c, sql)
        assert not out["success"] and "read-only" in out["error"], sql
    assert c.conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0] == 2


def test_csv_sql_vulnerable_mode_executes_delete():
    c = ctx(tool_defense=False)
    assert csv_sql(c, "DELETE FROM trips WHERE duration_min > 15")["success"]
    assert c.conn.execute("SELECT COUNT(*) FROM trips").fetchone()[0] == 1


def test_calculator_safe():
    assert calculator("29 + 0.17 * (120 - 45)", "USD")["data"] == {
        "value": 41.75,
        "units": "USD",
    }
    for bad in ["__import__('os')", "2**10", "1/0", "abs(-1)", "9" * 400]:
        assert not calculator(bad)["success"], bad


def test_policy_retriever_snapshot_and_untrusted_labels():
    with tempfile.TemporaryDirectory() as tmp:
        c = ctx(snapshot_dir=Path(tmp), prompt_defense=True)
        out = policy_retriever(c, str(FIXTURE), "month pass membership price", k=3)
        assert out["success"] and len(out["data"]["passages"]) == 3
        assert all(
            p["text"].startswith("<untrusted_web_text>")
            for p in out["data"]["passages"]
        )
        assert len(out["data"]["sha256"]) == 64
        assert (Path(tmp) / "pricing_snapshot.txt").exists()
    bad = policy_retriever(ctx(), "/no/such/file.html", "price")
    assert not bad["success"]


def test_gate_contract():
    assert is_destructive("rm -fr build") is True
    assert is_destructive("ls -la") is False
    blocked = confirm_bash("echo x > /etc/hosts")
    assert blocked["allow"] is False and blocked["reason"]
    assert confirm_bash("echo x > /etc/hosts", auto_approve=True)["allow"] is True
    assert confirm_bash("find . -name '*.pyc' -delete")["allow"] is False


def test_file_tools_sandbox():
    with tempfile.TemporaryDirectory() as tmp:
        tools = FileTools(tmp)
        tools.write_file("pkg/a.py", "x = 1\nDEBUG = True\n")
        assert tools.read_file("pkg/a.py", max_lines=1)["data"]["content"] == "x = 1"
        assert (
            "+DEBUG = False"
            in tools.edit_file("pkg/a.py", "DEBUG = True", "DEBUG = False")["data"][
                "diff"
            ]
        )
        assert tools.search_in_files("DEBUG", file_pattern="**/*.py")["data"]["matches"]
        assert not tools.read_file("../../etc/passwd")["success"]


def main() -> int:
    print("Kazi Samina Maraj Mumu")
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
            print(f"PASS {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
