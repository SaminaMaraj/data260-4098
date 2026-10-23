"""HW7 migration: add username + role to the MySQL users table and seed roles.

Run once from the repository root (MySQL container running, .env loaded):

    PYTHONPATH=. python code/migrate_hw07.py

Passwords are read from the environment (put them in your git-ignored .env):
    HW7_READER_PASSWORD, HW7_WRITER_PASSWORD, HW7_MODERATOR_PASSWORD

Only PBKDF2-SHA256 hashes are stored; plain-text passwords never reach MySQL.
The script is idempotent: running it twice does not duplicate anything.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
from sqlalchemy import inspect, select, text  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

from src.hw4_database import Base, db_session_basede26, engine  # noqa: E402
from src.hw4_models import User  # noqa: E402
from src.hw4_security import hash_password  # noqa: E402

PREFIX = "s4098"
SEED_USERS = [
    ("reader", f"{PREFIX}_reader", "HW7_READER_PASSWORD"),
    ("writer", f"{PREFIX}_writer", "HW7_WRITER_PASSWORD"),
    ("moderator", f"{PREFIX}_moderator", "HW7_MODERATOR_PASSWORD"),
]


def add_columns() -> list[str]:
    """Add the HW7 columns/constraints if they are missing."""
    done: list[str] = []
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("users")}
    with engine.begin() as conn:
        if "username" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(50) NULL"))
            done.append("added users.username")
        if "role" not in columns:
            conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN role VARCHAR(20) "
                    "NOT NULL DEFAULT 'reader'"
                )
            )
            done.append("added users.role (default reader)")

        # Existing HW4 users get a username derived from their email.
        rows = conn.execute(
            text("SELECT id, email FROM users WHERE username IS NULL")
        ).all()
        for user_id, email in rows:
            base = email.split("@", 1)[0].casefold()[:40]
            conn.execute(
                text("UPDATE users SET username = :u WHERE id = :id"),
                {"u": f"{base}_{user_id}", "id": user_id},
            )
        if rows:
            done.append(f"backfilled username for {len(rows)} existing user(s)")

    inspector = inspect(engine)
    index_names = {index["name"] for index in inspector.get_indexes("users")}
    unique_names = {item["name"] for item in inspector.get_unique_constraints("users")}
    if not ({"uq_users_username", "username"} & (index_names | unique_names)):
        with engine.begin() as conn:
            conn.execute(
                text("CREATE UNIQUE INDEX uq_users_username ON users (username)")
            )
        done.append("unique index on users.username")

    if engine.dialect.name == "mysql":
        with engine.begin() as conn:
            exists = conn.execute(
                text(
                    "SELECT COUNT(*) FROM information_schema.table_constraints "
                    "WHERE table_schema = DATABASE() AND table_name = 'users' "
                    "AND constraint_name = 'chk_users_role'"
                )
            ).scalar()
            if not exists:
                conn.execute(
                    text(
                        "ALTER TABLE users ADD CONSTRAINT chk_users_role "
                        "CHECK (role IN ('reader', 'writer', 'moderator'))"
                    )
                )
                done.append("CHECK constraint on users.role")
    return done


def seed_role_users() -> list[str]:
    done: list[str] = []
    db = db_session_basede26()
    try:
        for role, username, env_name in SEED_USERS:
            password = os.environ.get(env_name, "")
            if not password:
                raise SystemExit(f"Set {env_name} in .env before running this script.")
            user = db.scalar(select(User).where(User.username == username))
            if user is None:
                db.add(
                    User(
                        name=f"HW7 {role.title()}",
                        email=f"{username}@example.com",
                        username=username,
                        role=role,
                        password_hash=hash_password(password),
                    )
                )
                done.append(f"created {username} ({role})")
            else:
                user.role = role
                user.password_hash = hash_password(password)
                done.append(f"updated {username} ({role}) password hash")
        db.commit()
    finally:
        db.close()
    return done


def main() -> None:
    Base.metadata.create_all(bind=engine)  # no-op for existing tables
    for line in add_columns() + seed_role_users():
        print(" -", line)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, username, role, "
                "SUBSTR(password_hash, 1, 22) AS hash_prefix "
                "FROM users ORDER BY id"
            )
        ).all()
    print("\nusers table (password_hash truncated):")
    for row in rows:
        print(f"  {row.id:>3}  {row.username:<28} {row.role:<10} {row.hash_prefix}...")


if __name__ == "__main__":
    main()
