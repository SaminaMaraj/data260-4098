"""Municipal transit incident MCP server for DATA-260 HW5."" 

This server exposes exactly three MCP tools. All three return the shared
{ok, data, error} envelope from envelope.py and log only to stderr.
"""

from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import logging
import re
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import func, or_, select

from envelope import tool_envelope
from src.hw4_database import db_session_basede26
from src.hw4_models import IncidentRecord, Route


INCIDENT_CODE_PATTERN = re.compile(r"^INC-\d{6}$")
VALID_CATEGORIES = {
    "delay",
    "collision",
    "service-suspension",
    "infrastructure-issue",
}

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("hw5.transit")

mcp = FastMCP("transit")


def _incident_data(record: IncidentRecord, route: Route | None) -> dict[str, Any]:
    return {
        "id": record.id,
        "incident_code": record.incident_code,
        "incident_title": record.incident_title,
        "route_id": record.route_id,
        "route_line": record.route_line,
        "route_code": route.route_code if route else None,
        "route_name": route.route_name if route else None,
        "category": record.category,
        "passengers_affected": record.passengers_affected,
        "description": record.description,
        "submission_date": record.submission_date.isoformat(),
    }


def _error(message: str) -> dict[str, Any]:
    return tool_envelope(error=message)


@mcp.tool()
def search_incidents(
    query: str,
    category: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search incident code, title, route line, or description."""
    query = query.strip()
    if not query:
        return _error("query must not be empty")
    if not 1 <= limit <= 50:
        return _error("limit must be between 1 and 50")
    if category is not None and category not in VALID_CATEGORIES:
        return _error(f"unknown category: {category}")

    db = db_session_basede26()
    try:
        pattern = f"%{query}%"
        statement = (
            select(IncidentRecord, Route)
            .join(Route, IncidentRecord.route_id == Route.id)
            .where(
                or_(
                    IncidentRecord.incident_code.like(pattern),
                    IncidentRecord.incident_title.like(pattern),
                    IncidentRecord.route_line.like(pattern),
                    IncidentRecord.description.like(pattern),
                )
            )
            .order_by(IncidentRecord.id)
            .limit(limit)
        )
        if category is not None:
            statement = statement.where(IncidentRecord.category == category)

        rows = db.execute(statement).all()
        data = [_incident_data(record, route) for record, route in rows]
        return tool_envelope(data=data)
    except Exception as exc:
        logger.exception("Transit search failed")
        return _error(f"database operation failed: {exc}")
    finally:
        db.close()


@mcp.tool()
def get_incident(incident_code: str) -> dict[str, Any]:
    """Look up one incident by its validated incident code."""
    if not INCIDENT_CODE_PATTERN.fullmatch(incident_code.strip()):
        return _error("incident_code must match INC-######")

    db = db_session_basede26()
    try:
        row = db.execute(
            select(IncidentRecord, Route)
            .join(Route, IncidentRecord.route_id == Route.id)
            .where(IncidentRecord.incident_code == incident_code.strip())
        ).first()
        if row is None:
            return _error("incident not found")
        record, route = row
        return tool_envelope(data=_incident_data(record, route))
    except Exception as exc:
        logger.exception("Transit incident lookup failed")
        return _error(f"database operation failed: {exc}")
    finally:
        db.close()


@mcp.tool()
def incident_count_by_route(min_incidents: int = 0) -> dict[str, Any]:
    """Count incidents by Route, optionally filtering by a minimum count."""
    if min_incidents < 0:
        return _error("min_incidents must be greater than or equal to 0")

    db = db_session_basede26()
    try:
        statement = (
            select(
                Route.id,
                Route.route_code,
                Route.route_name,
                func.count(IncidentRecord.id).label("incident_count"),
            )
            .outerjoin(
                IncidentRecord,
                IncidentRecord.route_id == Route.id,
            )
            .group_by(Route.id, Route.route_code, Route.route_name)
            .having(func.count(IncidentRecord.id) >= min_incidents)
            .order_by(Route.id)
        )
        data = [
            {
                "route_id": route_id,
                "route_code": route_code,
                "route_name": route_name,
                "incident_count": int(incident_count),
            }
            for route_id, route_code, route_name, incident_count in db.execute(
                statement
            ).all()
        ]
        return tool_envelope(data=data)
    except Exception as exc:
        logger.exception("Transit aggregate failed")
        return _error(f"database operation failed: {exc}")
    finally:
        db.close()


if __name__ == "__main__":
    mcp.run(transport="stdio")
