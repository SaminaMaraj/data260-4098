"""Incident domain logic for the Kafka worker (no Kafka code in here).

CREATE_INCIDENT / GET_INCIDENT on a plain Python dict, plus an idempotency
cache keyed by correlation_id (Part 3: duplicate delivery).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

# Same rules as the HW4 incident schema (DOMAIN_SCHEMA.md)
VALID_CATEGORIES = {"delay", "collision", "service-suspension", "infrastructure-issue"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
REQUIRED_FIELDS = (
    "incidentTitle",
    "routeLine",
    "submitterEmail",
    "description",
    "category",
    "termsAccepted",
)
ALLOWED_FIELDS = set(REQUIRED_FIELDS) | {"passengersAffected"}
OPERATIONS = ("CREATE_INCIDENT", "GET_INCIDENT")


def _text(data: dict, field: str, lo: int, hi: int) -> str | None:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        return f"{field} is required and must be a non-empty string"
    if not lo <= len(value.strip()) <= hi:
        return f"{field} must be {lo}-{hi} characters"
    return None


def validate_incident(data: Any) -> str | None:
    """Return None if valid, otherwise one clean error message."""
    if not isinstance(data, dict):
        return "data must be a JSON object"
    missing = [f for f in REQUIRED_FIELDS if f not in data or data[f] in (None, "")]
    if missing:
        return "Missing required field(s): " + ", ".join(missing)
    unknown = sorted(set(data) - ALLOWED_FIELDS)
    if unknown:
        return "Unknown field(s): " + ", ".join(unknown)
    for field, lo, hi in (
        ("incidentTitle", 3, 100),
        ("routeLine", 2, 100),
        ("description", 26, 1000),
    ):
        error = _text(data, field, lo, hi)
        if error:
            return error
    email = data["submitterEmail"]
    if not isinstance(email, str) or not EMAIL_RE.match(email.strip()):
        return "submitterEmail must be a valid email address"
    if data["category"] not in VALID_CATEGORIES:
        return "category must be one of: " + ", ".join(sorted(VALID_CATEGORIES))
    if data["termsAccepted"] is not True:
        return "termsAccepted must be true"
    passengers = data.get("passengersAffected", 0)
    if (
        isinstance(passengers, bool)
        or not isinstance(passengers, int)
        or passengers < 0
    ):
        return "passengersAffected must be an integer >= 0"
    return None


class IncidentService:
    """In-memory incident store + idempotent request processing."""

    def __init__(self, idempotency: bool = True):
        self.incidents: dict[str, dict] = {}
        self.idempotency = idempotency
        # correlation_id -> the response that was sent the first time
        self.processed: dict[str, dict] = {}

    def handle(self, request: dict) -> tuple[dict, bool]:
        """Process one request message. Returns (response, was_duplicate)."""
        cid = request.get("correlation_id")
        if self.idempotency and cid in self.processed:
            return dict(self.processed[cid]), True
        response = self._process(request)
        response = {"correlation_id": cid, **response}
        # cache only finished CREATEs: replaying one must not create a 2nd incident
        if self.idempotency and cid and request.get("operation") == "CREATE_INCIDENT":
            self.processed[cid] = response
        return response, False

    def _process(self, request: dict) -> dict:
        operation = request.get("operation")
        data = request.get("data")
        if operation not in OPERATIONS:
            return {
                "success": False,
                "operation": operation,
                "error": "Unknown operation",
            }
        if operation == "CREATE_INCIDENT":
            error = validate_incident(data)
            if error:
                return {"success": False, "operation": operation, "error": error}
            incident_id = str(uuid.uuid4())
            record = {
                "incident_id": incident_id,
                **{
                    k: (v.strip() if isinstance(v, str) else v) for k, v in data.items()
                },
                "passengersAffected": data.get("passengersAffected", 0),
                "submissionDate": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"
                ),
            }
            self.incidents[incident_id] = record
            return {
                "success": True,
                "operation": operation,
                "incident_id": incident_id,
                "message": "Incident created",
            }
        # GET_INCIDENT
        if not isinstance(data, dict) or not data.get("incident_id"):
            return {
                "success": False,
                "operation": operation,
                "error": "incident_id is required",
            }
        incident = self.incidents.get(str(data["incident_id"]))
        if incident is None:
            return {
                "success": False,
                "operation": operation,
                "error": "Incident not found",
            }
        return {"success": True, "operation": operation, "incident": dict(incident)}
