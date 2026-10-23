"""Offline HW7 auth/RBAC tests (SQLite stand-in for MySQL, no server needed).

python tests/test_hw07_auth.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

_TMP = tempfile.mkdtemp(prefix="hw07_auth_")
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_TMP}/auth.db"
os.environ.setdefault("JWT_SECRET_KEY", "offline-test-secret-key-for-hw07-auth-tests")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.hw4_api import router as domain_router  # noqa: E402
from src.hw4_database import Base, db_session_basede26, engine  # noqa: E402
from src.hw4_models import Route, User  # noqa: E402
from src.hw4_security import hash_password  # noqa: E402
from src.hw7_auth import create_access_token  # noqa: E402
from src.hw7_auth import router as auth_router

PASSWORDS = {"reader": "r-pass-1", "writer": "w-pass-1", "moderator": "m-pass-1"}


def build_client() -> TestClient:
    Base.metadata.create_all(bind=engine)
    db = db_session_basede26()
    for role, password in PASSWORDS.items():
        db.add(
            User(
                name=role,
                email=f"{role}@example.com",
                username=f"s4098_{role}",
                role=role,
                password_hash=hash_password(password),
            )
        )
    db.add(Route(route_name="VTA Route 22", operator="VTA", route_code="RT-001"))
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(domain_router)
    return TestClient(app)


client = build_client()


def token(role: str) -> str:
    response = client.post(
        "/auth/login",
        json={"username": f"s4098_{role}", "password": PASSWORDS[role]},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def bearer(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(role)}"}


def new_incident(code: str) -> dict:
    return {
        "incidentCode": code,
        "incidentTitle": "HW7 RBAC test incident",
        "routeLine": "VTA Route 22",
        "routeId": 1,
        "submitterEmail": "writer@example.com",
        "description": "Created by the offline HW7 role-based access test.",
        "category": "delay",
        "passengersAffected": 1,
        "termsAccepted": True,
    }


def test_login_valid_returns_jwt():
    response = client.post(
        "/auth/login", json={"username": "s4098_reader", "password": "r-pass-1"}
    )
    body = response.json()
    assert response.status_code == 200
    assert body["token_type"] == "bearer" and body["access_token"].count(".") == 2


def test_login_invalid_returns_401():
    response = client.post(
        "/auth/login", json={"username": "s4098_reader", "password": "wrong"}
    )
    assert response.status_code == 401


def test_me_without_token_401():
    assert client.get("/auth/me").status_code == 401


def test_me_with_invalid_token_401():
    headers = {"Authorization": "Bearer not.a.jwt"}
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_me_with_expired_token_401():
    db = db_session_basede26()
    user = db.query(User).filter_by(username="s4098_reader").one()
    expired = create_access_token(user, expires_delta=timedelta(minutes=-1))
    db.close()
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401 and "expired" in response.json()["detail"]


def test_me_returns_identity_and_role():
    body = client.get("/auth/me", headers=bearer("writer")).json()
    assert body["username"] == "s4098_writer" and body["role"] == "writer"


def test_list_any_role_200():
    for role in PASSWORDS:
        assert client.get("/api/hw4/incidents", headers=bearer(role)).status_code == 200


def test_create_reader_403_writer_201():
    payload = new_incident("INC-970001")
    assert (
        client.post("/api/hw4/incidents", json=payload, headers=bearer("reader"))
    ).status_code == 403
    assert (
        client.post("/api/hw4/incidents", json=payload, headers=bearer("writer"))
    ).status_code == 201


def test_delete_writer_403_moderator_200():
    created = client.post(
        "/api/hw4/incidents",
        json=new_incident("INC-970002"),
        headers=bearer("moderator"),
    ).json()
    url = f"/api/hw4/incidents/{created['id']}"
    assert client.delete(url, headers=bearer("writer")).status_code == 403
    assert client.delete(url, headers=bearer("moderator")).status_code == 200


def main() -> int:
    print("Kazi Samina Maraj Mumu")
    tests = [value for name, value in globals().items() if name.startswith("test_")]
    passed = 0
    for test in tests:
        try:
            test()
            passed += 1
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            print(f"FAIL {test.__name__}: {exc}")
    print(f"{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
