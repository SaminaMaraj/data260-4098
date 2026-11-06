"""HW9 Part 1: Redis-backed view counter for the Incident entity.

Every access does one Redis INCR (fast, atomic). Only every SYNC_EVERY-th
access writes the count to the incidents row in s4098_rel, so the database
gets 1 write per 10 views instead of 1 read + 1 write per view.
"""

from __future__ import annotations

import redis
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.hw9_cache.config import SYNC_EVERY, VIEW_KEY, log


class IncidentStoreWithCache:
    """s4098_rel incidents table with a Redis cache in front of it."""

    def __init__(
        self,
        engine: Engine,
        redis_client: redis.Redis,
        sync_every: int = SYNC_EVERY,
        verbose: bool = True,
    ):
        self.engine = engine
        self.redis_client = redis_client
        self.sync_every = sync_every
        self.verbose = verbose
        self.db_writes = 0
        self.last_synced: int | None = None  # count of the most recent DB sync

    @staticmethod
    def views_key(incident_id: int) -> str:
        return VIEW_KEY.format(incident_id=incident_id)

    def increment_incident_views(self, incident_id: int) -> int:
        """Count one access of an incident and return the current total."""
        key = self.views_key(incident_id)
        # 1. increment in Redis (INCR is atomic, so concurrent views are not lost)
        count = self.redis_client.incr(key)
        # 2. every 10th increment, persist the count to the database row
        if count % self.sync_every == 0:
            with self.engine.begin() as conn:
                conn.execute(
                    text("UPDATE incidents SET view_count = :c WHERE id = :id"),
                    {"c": count, "id": incident_id},
                )
            self.db_writes += 1
            self.last_synced = count
            if self.verbose:
                print("✓ Synced views to database", flush=True)
                log(
                    "VIEWS",
                    f"UPDATE incidents SET view_count={count} WHERE id={incident_id}",
                )
        # 3. return the current count
        return count

    # helpers for the demo -------------------------------------------------
    def db_view_count(self, incident_id: int) -> int:
        with self.engine.connect() as conn:
            return int(
                conn.execute(
                    text("SELECT view_count FROM incidents WHERE id = :id"),
                    {"id": incident_id},
                ).scalar_one()
            )

    def reset(self, incident_id: int) -> None:
        self.redis_client.delete(self.views_key(incident_id))
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE incidents SET view_count = 0 WHERE id = :id"),
                {"id": incident_id},
            )

    def increment_views_db_only(self, incident_id: int) -> int:
        """Baseline for the timing comparison: read + write the DB on every view."""
        with self.engine.begin() as conn:
            conn.execute(
                text("UPDATE incidents SET view_count = view_count + 1 WHERE id = :id"),
                {"id": incident_id},
            )
            return int(
                conn.execute(
                    text("SELECT view_count FROM incidents WHERE id = :id"),
                    {"id": incident_id},
                ).scalar_one()
            )
