"""Offline plain-Python tests using real transit tools and fake data access."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = REPO_ROOT / "code"
MCP_DIR = CODE_DIR / "mcp"

# Prevent code/ from shadowing the installed mcp package.
sys.path[:] = [
    item
    for item in sys.path
    if Path(item or ".").resolve() != CODE_DIR.resolve()
]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(MCP_DIR))

# Importing the real transit module must not require the MySQL container.
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

from envelope import tool_envelope
from execute_tool import configure_tool_registry, execute_tool
from agent import MockModel, run_agent
from transit_server import (
    configure_data_source,
    incident_count_by_route,
    get_incident,
    search_incidents,
)


class FakeTransitDataSource:
    """Small in-memory replacement for the transit server's DB access."""

    def __init__(self):
        self.routes = [
            SimpleNamespace(id=1, route_code="RT-001", route_name="VTA Route 22"),
            SimpleNamespace(id=2, route_code="RT-002", route_name="VTA Green Line"),
        ]
        self.incidents = [
            SimpleNamespace(
                id=2,
                incident_code="INC-000002",
                incident_title="Bus delay",
                route_id=1,
                route_line="VTA Route 22",
                category="delay",
                passengers_affected=3,
                description="A seeded delay near the station.",
                submission_date=datetime(2026, 1, 1),
            ),
            SimpleNamespace(
                id=3,
                incident_code="INC-000003",
                incident_title="Track collision",
                route_id=2,
                route_line="VTA Green Line",
                category="collision",
                passengers_affected=5,
                description="A collision affected service.",
                submission_date=datetime(2026, 1, 2),
            ),
        ]

    def _route_for(self, route_id):
        return next(route for route in self.routes if route.id == route_id)

    def search_incidents(self, query, category, limit):
        query_lower = query.casefold()
        rows = []
        for incident in self.incidents:
            searchable = " ".join(
                [
                    incident.incident_code,
                    incident.incident_title,
                    incident.route_line,
                    incident.description,
                ]
            ).casefold()
            if query_lower in searchable and (
                category is None or incident.category == category
            ):
                rows.append((incident, self._route_for(incident.route_id)))
        return rows[:limit]

    def get_incident(self, incident_code):
        incident = next(
            (
                incident
                for incident in self.incidents
                if incident.incident_code == incident_code
            ),
            None,
        )
        if incident is None:
            return None
        return incident, self._route_for(incident.route_id)

    def incident_count_by_route(self, min_incidents):
        results = []
        for route in self.routes:
            count = sum(
                incident.route_id == route.id for incident in self.incidents
            )
            if count >= min_incidents:
                results.append(
                    {
                        "route_id": route.id,
                        "route_code": route.route_code,
                        "route_name": route.route_name,
                        "incident_count": count,
                    }
                )
        return results


def payload(result):
    parsed = json.loads(result)
    assert set(parsed) == {"ok", "data", "error"}
    return parsed


def test_valid_search():
    result = payload(
        execute_tool(
            "search_incidents",
            {"query": "delay", "category": "delay", "limit": 5},
        )
    )
    assert result["ok"] is True
    assert result["data"][0]["incident_code"] == "INC-000002"


def test_valid_get():
    result = payload(
        execute_tool("get_incident", {"incident_code": "INC-000002"})
    )
    assert result["ok"] is True
    assert result["data"]["route_code"] == "RT-001"


def test_valid_aggregate():
    result = payload(
        execute_tool("incident_count_by_route", {"min_incidents": 0})
    )
    assert result["ok"] is True
    assert len(result["data"]) == 2


def test_invalid_unknown_category():
    result = payload(
        execute_tool(
            "search_incidents",
            {"query": "delay", "category": "unknown-category", "limit": 10},
        )
    )
    assert result == {
        "ok": False,
        "data": None,
        "error": "unknown category: unknown-category",
    }


def test_invalid_incident_code():
    result = payload(execute_tool("get_incident", {"incident_code": "abc"}))
    assert result == {
        "ok": False,
        "data": None,
        "error": "incident_code must match INC-######",
    }


def test_invalid_minimum():
    result = payload(
        execute_tool("incident_count_by_route", {"min_incidents": -5})
    )
    assert result == {
        "ok": False,
        "data": None,
        "error": "min_incidents must be greater than or equal to 0",
    }


def test_unknown_tool():
    result = payload(execute_tool("not_a_domain_tool", {}))
    assert result == {
        "ok": False,
        "data": None,
        "error": "unknown tool name: not_a_domain_tool",
    }


def test_safety_limit_block():
    result = payload(
        execute_tool(
            "search_incidents",
            {"query": "delay", "limit": 51},
        )
    )
    assert result == {
        "ok": False,
        "data": None,
        "error": "safety policy: search limit cannot exceed 50",
    }


def test_agent_stops_at_max_steps():
    result = run_agent(
        "Keep using the route-count tool.",
        model=MockModel(),
        max_steps=2,
    )
    assert result["stop_reason"] == "max_steps"
    assert result["steps"] == 2
    assert result["tool_calls"] == 2


def main():
    fake_source = FakeTransitDataSource()
    configure_data_source(fake_source)
    configure_tool_registry(
        {
            "search_incidents": search_incidents,
            "get_incident": get_incident,
            "incident_count_by_route": incident_count_by_route,
        }
    )

    tests = [
        test_valid_search,
        test_valid_get,
        test_valid_aggregate,
        test_invalid_unknown_category,
        test_invalid_incident_code,
        test_invalid_minimum,
        test_unknown_tool,
        test_safety_limit_block,
        test_agent_stops_at_max_steps,
    ]
    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
            print(f"PASS {test.__name__}")
        except Exception as exc:
            print(f"FAIL {test.__name__}: {exc}")

    configure_data_source(None)
    configure_tool_registry(None)
    print(f"{passed}/{len(tests)} passed")
    if passed != len(tests):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
