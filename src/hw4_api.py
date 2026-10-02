import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from fastapi import Depends
from sqlalchemy.orm import Session

from src.hw4_models import IncidentRecord as Incident

from .hw4_database import get_db
from .hw4_models import IncidentRecord, Route, SessionToken, User
from .hw4_schemas import (
    IncidentCreate,
    IncidentResponse,
    IncidentUpdate,
    LoginRequest,
    RegisterRequest,
    RouteCreate,
    RouteResponse,
    RouteUpdate,
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
        incidentCode=record.incident_code,
        incidentTitle=record.incident_title,
        routeLine=record.route_line,
        routeId=record.route_id,
        submitterEmail=record.submitter_email,
        description=record.description,
        category=record.category,
        passengersAffected=record.passengers_affected,
        termsAccepted=record.terms_accepted,
        submissionDate=record.submission_date.isoformat(),
        createdAt=record.created_at,
        updatedAt=record.updated_at,
        related=[
            {
                "id": item.id,
                "related_type": item.related_type,
                "related_text": item.related_text,
            }
            for item in record.related_items
        ],
    )


def route_response(route: Route) -> RouteResponse:
    return RouteResponse(
        id=route.id,
        routeName=route.route_name,
        operator=route.operator,
        routeCode=route.route_code,
        createdAt=route.created_at,
        updatedAt=route.updated_at,
    )


def route_for_payload(
    route_id: int | None,
    route_line: str,
    db: Session,
) -> Route:
    if route_id is not None:
        route = db.get(Route, route_id)
        if route is None:
            raise HTTPException(status_code=404, detail="Route not found")
        return route

    route = db.scalar(
        select(Route).where(Route.route_name == route_line)
    )

    if route is None:
        raise HTTPException(
            status_code=422,
            detail="routeId is required when routeLine is not an existing route",
        )

    return route


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


@router.post(
    "/routes",
    response_model=RouteResponse,
    status_code=201,
)
def create_route(
    payload: RouteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    del user

    route = Route(
        route_name=payload.routeName.strip(),
        operator=payload.operator.strip(),
        route_code=payload.routeCode.upper(),
    )
    db.add(route)

    try:
        db.commit()
        db.refresh(route)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Route code already exists",
        )

    return route_response(route)


@router.get("/routes", response_model=list[RouteResponse])
def list_routes(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    del user

    limit = min(max(limit, 1), 200)
    routes = db.scalars(
        select(Route)
        .order_by(Route.id)
        .offset(skip)
        .limit(limit)
    ).all()
    return [route_response(route) for route in routes]


@router.get("/routes/{route_id}", response_model=RouteResponse)
def get_route(
    route_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    del user

    route = db.get(Route, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")
    return route_response(route)


@router.put("/routes/{route_id}", response_model=RouteResponse)
def update_route(
    route_id: int,
    payload: RouteUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    del user

    route = db.get(Route, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")

    route.route_name = payload.routeName.strip()
    route.operator = payload.operator.strip()
    route.route_code = payload.routeCode.upper()

    try:
        db.commit()
        db.refresh(route)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Route code already exists",
        )

    return route_response(route)


@router.delete("/routes/{route_id}")
def delete_route(
    route_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    del user

    route = db.get(Route, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail="Route not found")

    incident_count = db.scalar(
        select(func.count())
        .select_from(IncidentRecord)
        .where(IncidentRecord.route_id == route_id)
    )
    if incident_count:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a route that still has incidents",
        )

    db.delete(route)
    db.commit()
    return {"message": "Route deleted", "id": route_id}


@router.get(
    "/routes/{route_id}/incidents",
    response_model=list[IncidentResponse],
)
def route_incidents(
    route_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    del user

    if db.get(Route, route_id) is None:
        raise HTTPException(status_code=404, detail="Route not found")

    limit = min(max(limit, 1), 200)
    records = db.scalars(
        select(IncidentRecord)
        .options(selectinload(IncidentRecord.related_items))
        .where(IncidentRecord.route_id == route_id)
        .order_by(IncidentRecord.id)
        .offset(skip)
        .limit(limit)
    ).all()
    return [incident_response(record) for record in records]


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

    route_line = payload.routeLine.strip()
    route = route_for_payload(payload.routeId, route_line, db)

    if db.scalar(
        select(IncidentRecord).where(
            IncidentRecord.incident_code == payload.incidentCode.upper()
        )
    ):
        raise HTTPException(
            status_code=409,
            detail="Incident code already exists",
        )

    record = IncidentRecord(
        incident_code=payload.incidentCode.upper(),
        incident_title=payload.incidentTitle.strip(),
        route_line=route_line,
        route_id=route.id,
        submitter_email=str(payload.submitterEmail).lower(),
        description=payload.description.strip(),
        category=payload.category,
        passengers_affected=payload.passengersAffected,
        terms_accepted=payload.termsAccepted,
    )

    db.add(record)
    try:
        db.commit()
        db.refresh(record)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Incident code already exists",
        )

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

    route_line = payload.routeLine.strip()
    route = route_for_payload(payload.routeId, route_line, db)

    duplicate = db.scalar(
        select(IncidentRecord).where(
            IncidentRecord.incident_code == payload.incidentCode.upper(),
            IncidentRecord.id != incident_id,
        )
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="Incident code already exists",
        )

    record.incident_code = payload.incidentCode.upper()
    record.incident_title = payload.incidentTitle.strip()
    record.route_line = route_line
    record.route_id = route.id
    record.submitter_email = str(payload.submitterEmail).lower()
    record.description = payload.description.strip()
    record.category = payload.category
    record.passengers_affected = payload.passengersAffected
    record.terms_accepted = payload.termsAccepted

    try:
        db.commit()
        db.refresh(record)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Incident code already exists",
        )

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
