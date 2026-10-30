"""Offline HW8 tests (no Kafka needed): incident logic, idempotency, poison check,
VERIFY_SEED message generator.   python tests/test_hw08.py"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "code" / "hw8"))

from src.hw8_kafka.agent_runtime import PoisonMessage  # noqa: E402
from src.hw8_kafka.agents import check_task  # noqa: E402
from src.hw8_kafka.incidents import IncidentService, validate_incident  # noqa: E402

GOOD = {
    "incidentTitle": "Signal failure",
    "routeLine": "VTA Blue Line",
    "submitterEmail": "rider@example.com",
    "description": "Signal failure near Tasman station caused a 15 minute delay.",
    "category": "delay",
    "termsAccepted": True,
}


def req(op, data, cid=None):
    return {
        "correlation_id": cid or str(uuid.uuid4()),
        "reply_to": "s4098_entity_responses",
        "operation": op,
        "data": data,
    }


def test_create_get_round_trip():
    s = IncidentService()
    r, _ = s.handle(req("CREATE_INCIDENT", GOOD, "c1"))
    assert r["success"] and r["correlation_id"] == "c1"
    uuid.UUID(r["incident_id"])
    g, _ = s.handle(req("GET_INCIDENT", {"incident_id": r["incident_id"]}, "c2"))
    assert g["success"] and g["correlation_id"] == "c2"
    assert all(g["incident"][k] == v for k, v in GOOD.items())


def test_validation_rejects_bad_values():
    assert validate_incident(GOOD) is None
    for change in (
        {"incidentTitle": ""},
        {"submitterEmail": "not-an-email"},
        {"category": "weather"},
        {"termsAccepted": False},
        {"description": "too short"},
        {"passengersAffected": -1},
        {"userId": 7},
    ):
        assert validate_incident({**GOOD, **change}) is not None, change
    missing = dict(GOOD)
    missing.pop("routeLine")
    assert "routeLine" in validate_incident(missing)


def test_errors_keep_correlation_id():
    s = IncidentService()
    for r in (
        s.handle(req("DELETE_INCIDENT", {}, "x1"))[0],
        s.handle(req("GET_INCIDENT", {"incident_id": "nope"}, "x2"))[0],
        s.handle(req("CREATE_INCIDENT", {**GOOD, "category": "?"}, "x3"))[0],
    ):
        assert (
            r["success"] is False and r["error"] and r["correlation_id"].startswith("x")
        )
    assert s.handle(req("DELETE_INCIDENT", {}))[0]["error"] == "Unknown operation"
    assert (
        s.handle(req("GET_INCIDENT", {"incident_id": "nope"}))[0]["error"]
        == "Incident not found"
    )


def test_idempotent_replay_creates_one_incident():
    s = IncidentService(idempotency=True)
    first, dup1 = s.handle(req("CREATE_INCIDENT", GOOD, "same"))
    second, dup2 = s.handle(req("CREATE_INCIDENT", GOOD, "same"))
    assert (dup1, dup2) == (False, True)
    assert first == second and len(s.incidents) == 1


def test_without_idempotency_replay_duplicates():
    s = IncidentService(idempotency=False)
    a, _ = s.handle(req("CREATE_INCIDENT", GOOD, "same"))
    b, _ = s.handle(req("CREATE_INCIDENT", GOOD, "same"))
    assert a["incident_id"] != b["incident_id"] and len(s.incidents) == 2


def test_poison_task_detected():
    check_task({"plan": {"steps": ["a"]}})
    for bad in (
        {"plan": "<<corrupted plan>>"},
        {},
        {"plan": {"steps": []}},
        {"plan": {"steps": [1]}},
    ):
        try:
            check_task(bad)
        except PoisonMessage:
            continue
        raise AssertionError(f"not rejected: {bad}")


def test_ordering_messages_seeded():
    from run_failure_tests import ordering_messages

    a, b = ordering_messages(), ordering_messages()
    assert a == b and len(a) == 20
    incidents = {m["incident_id"] for m in a}
    assert len(incidents) == 4
    for incident in incidents:
        assert [m["seq"] for m in a if m["incident_id"] == incident] == [1, 2, 3, 4, 5]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
