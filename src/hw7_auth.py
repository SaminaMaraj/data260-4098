"""HW7 JWT bearer authentication and role-based authorization.

The HW4 cookie-session login stays in history at the ``hw4`` tag. From HW7 on,
the graded domain routes (``/api/hw4/routes`` and ``/api/hw4/incidents``)
accept only ``Authorization: Bearer <JWT>``.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .hw4_database import get_db
from .hw4_models import User
from .hw4_security import verify_password

Role = Literal["reader", "writer", "moderator"]
VALID_ROLES: tuple[str, ...] = ("reader", "writer", "moderator")

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY", "dev-only-change-me-s4098-local-jwt-secret-key"
)
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))

bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/auth", tags=["HW7 JWT auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: Role


class MeResponse(BaseModel):
    id: int
    username: str
    role: Role
    name: str
    email: str


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_access_token(
    user: User,
    expires_delta: timedelta | None = None,
) -> str:
    """Sign a short-lived HS256 token carrying the username and role."""
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub": user.username,
        "uid": user.id,
        "role": user.role,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Return the user for a valid bearer token, otherwise raise 401."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Not authenticated: missing bearer token")

    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthorized("Invalid token") from exc

    user = db.scalar(select(User).where(User.username == payload["sub"]))
    if user is None:
        raise _unauthorized("Invalid token: user no longer exists")
    return user


def require_roles(*allowed: str) -> Callable[..., User]:
    """Dependency factory: 401 without a valid token, 403 for the wrong role."""
    unknown = set(allowed) - set(VALID_ROLES)
    if unknown:
        raise ValueError(f"unknown role(s): {sorted(unknown)}")

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Forbidden: role '{user.role}' cannot perform this action "
                    f"(requires {' or '.join(allowed)})"
                ),
            )
        return user

    return checker


# Role policy for the domain routes.
any_role = require_roles("reader", "writer", "moderator")
writer_or_moderator = require_roles("writer", "moderator")
moderator_only = require_roles("moderator")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Verify the hashed password stored in MySQL, then issue a JWT."""
    user = db.scalar(
        select(User).where(User.username == payload.username.strip().casefold())
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise _unauthorized("Invalid username or password")

    return TokenResponse(
        access_token=create_access_token(user),
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        role=user.role,
    )


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        name=user.name,
        email=user.email,
    )
