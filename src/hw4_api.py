import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from fastapi import Depends
from sqlalchemy.orm import Session

from src.hw4_models import IncidentRecord as Incident

from .hw4_database import get_db
from .hw4_models import IncidentRecord, SessionToken, User
from .hw4_schemas import (
    IncidentCreate,
    IncidentResponse,
    IncidentUpdate,
    LoginRequest,
    RegisterRequest,
    UserResponse,
)
from .hw4_security import hash_password, verify_password


router = APIRouter(prefix="/api/hw4", tags=["HW4"])

SESSION_COOKIE = "hw4_session"
SESSION_TTL_SECONDS = 30 * 60

VALID_CATEGORIES = {
    "delay",
    "collision",
    "service-suspension",
    "infrastructure-issue",
}


def require_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    token = request.cookies.get(SESSION_COOKIE)

    if not token:
        raise HTTPException(status_code=401, detail="Login required")

    session = db.get(SessionToken, token)

    if session is None:
        raise HTTPException(status_code=401, detail="Invalid session")

    if session.expires_at <= datetime.utcnow():
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired")

    user = db.get(User, session.user_id)

    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def incident_response(record: IncidentRecord) -> IncidentResponse:
    return IncidentResponse(
        id=record.id,
        incidentTitle=record.incident_title,
        routeLine=record.route_line,
        submitterEmail=record.submitter_email,
        description=record.description,
        category=record.category,
        termsAccepted=record.terms_accepted,
        submissionDate=record.submission_date.isoformat(),
        related=[
            {
                "id": item.id,
                "related_type": item.related_type,
                "related_text": item.related_text,
            }
            for item in record.related_items
        ],
    )


@router.post("/auth/register", response_model=UserResponse, status_code=201)
def register(
    payload: RegisterRequest,
    db: Session = Depends(get_db),
):
    email = str(payload.email).lower()

    existing = db.scalar(
        select(User).where(User.email == email)
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        )

    user = User(
        name=payload.name.strip(),
        email=email,
        password_hash=hash_password(payload.password),
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        )

    return user


@router.post("/auth/login")
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    email = str(payload.email).lower()

    user = db.scalar(
        select(User).where(User.email == email)
    )

    if user is None or not verify_password(
        payload.password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    token = secrets.token_urlsafe(48)
    expires_at = datetime.utcnow() + timedelta(
        seconds=SESSION_TTL_SECONDS
    )

    session = SessionToken(
        id=token,
        user_id=user.id,
        expires_at=expires_at,
    )

    db.add(session)
    db.commit()

    secure_cookie = os.getenv("HW4_COOKIE_SECURE", "0") == "1"

    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
    )

    return {
        "message": "Login successful",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
        },
    }


@router.get("/auth/me", response_model=UserResponse)
def current_user(
    user: User = Depends(require_user),
):
    return user


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    token = request.cookies.get(SESSION_COOKIE)

    if token:
        session = db.get(SessionToken, token)

        if session:
            db.delete(session)
            db.commit()

    response.delete_cookie(SESSION_COOKIE)

    return {"message": "Logged out"}


@router.get(
    "/incidents",
    response_model=list[IncidentResponse],
)
def list_incidents(
    q: str = "",
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    del user

    limit = min(max(limit, 1), 200)

    statement = (
        select(IncidentRecord)
        .options(selectinload(IncidentRecord.related_items))
        .order_by(IncidentRecord.id)
        .offset(skip)
        .limit(limit)
    )

    search = q.strip()

    if search:
        pattern = f"%{search}%"
        statement = statement.where(
            or_(
                IncidentRecord.incident_title.like(pattern),
                IncidentRecord.route_line.like(pattern),
            )
        )

    records = db.scalars(statement).all()

    return [incident_response(record) for record in records]


@router.get(
    "/incidents/{incident_id}",
    response_model=IncidentResponse,
)
def get_incident(
    incident_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    del user

    statement = (
        select(IncidentRecord)
        .options(selectinload(IncidentRecord.related_items))
        .where(IncidentRecord.id == incident_id)
    )

    record = db.scalar(statement)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    return incident_response(record)


@router.post(
    "/incidents",
    response_model=IncidentResponse,
    status_code=201,
)
def create_incident(
    payload: IncidentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    del user

    if payload.category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail="Invalid incident category",
        )

    record = IncidentRecord(
        incident_title=payload.incidentTitle.strip(),
        route_line=payload.routeLine.strip(),
        submitter_email=str(payload.submitterEmail).lower(),
        description=payload.description.strip(),
        category=payload.category,
        terms_accepted=payload.termsAccepted,
    )

    db.add(record)
    db.commit()
    db.refresh(record)

    return incident_response(record)


@router.put(
    "/incidents/{incident_id}",
    response_model=IncidentResponse,
)
def update_incident(
    incident_id: int,
    payload: IncidentUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    del user

    record = db.get(IncidentRecord, incident_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    if payload.category not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail="Invalid incident category",
        )

    record.incident_title = payload.incidentTitle.strip()
    record.route_line = payload.routeLine.strip()
    record.submitter_email = str(payload.submitterEmail).lower()
    record.description = payload.description.strip()
    record.category = payload.category
    record.terms_accepted = payload.termsAccepted

    db.commit()
    db.refresh(record)

    return incident_response(record)


@router.delete("/incidents/{incident_id}")
def delete_incident(
    incident_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    del user

    record = db.get(IncidentRecord, incident_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail="Incident not found",
        )

    db.delete(record)
    db.commit()

    return {
        "message": "Incident deleted",
        "id": incident_id,
    }