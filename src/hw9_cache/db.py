"""Access to the s4098_rel relational database (MySQL from HW4/HW5).

Uses the same DATABASE_URL from .env as HW4-HW7. HW9 only needs plain SQL, so
the ORM models are not changed (incidents.view_count is added by
code/hw9/migrate_hw09.py).
"""

from __future__ import annotations

import redis
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from src.hw9_cache.config import REDIS_URL


def get_engine() -> Engine:
    from src.hw4_database import engine  # loads .env / DATABASE_URL

    return engine


def get_redis(url: str = REDIS_URL) -> redis.Redis:
    client = redis.Redis.from_url(url, decode_responses=True)
    client.ping()
    return client


def ensure_view_count_column(engine: Engine) -> bool:
    """Add incidents.view_count if it is missing. Returns True if it was added."""
    columns = {c["name"] for c in inspect(engine).get_columns("incidents")}
    if "view_count" in columns:
        return False
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE incidents ADD COLUMN view_count INT NOT NULL DEFAULT 0")
        )
    return True


def incident_by_code(engine: Engine, code: str) -> dict | None:
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT id, incident_code, incident_title, route_line, category, "
                    "passengers_affected, submission_date, view_count "
                    "FROM incidents WHERE incident_code = :c"
                ),
                {"c": code},
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None
