"""Transit incident and route CRUD API.

HW7: these graded domain routes use JWT bearer authentication with roles.
The HW4 cookie-session login is kept only as history at the ``hw4`` tag.

Role policy
- list / read  : reader, writer, moderator
- create/update: writer, moderator
- delete       : moderator
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .hw4_database import get_db
from .hw4_models import IncidentRecord, Route, User
from .hw4_schemas import (
    IncidentCreate,
    IncidentResponse,
    IncidentUpdate,
    RouteCreate,
    RouteResponse,
    RouteUpdate,
)
from .hw7_auth import any_role, moderator_only, writer_or_moderator

router = APIRouter(prefix="/api/hw4", tags=["HW4 domain API (JWT since HW7)"])

VALID_CATEGORIES = {
    "delay",
    "collision",
    "service-suspension",
    "infrastructure-issue",
}


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

    route = db.scalar(select(Route).where(Route.route_name == route_line))

    if route is None:
        raise HTTPException(
            status_code=422,
            detail="routeId is required when routeLine is not an existing route",
        )

    return route


@router.post(
    "/routes",
    response_model=RouteResponse,
    status_code=201,
)
def create_route(
    payload: RouteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(writer_or_moderator),
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
    user: User = Depends(any_role),
):
    del user

    limit = min(max(limit, 1), 200)
    routes = db.scalars(
        select(Route).order_by(Route.id).offset(skip).limit(limit)
    ).all()
    return [route_response(route) for route in routes]


@router.get("/routes/{route_id}", response_model=RouteResponse)
def get_route(
    route_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(any_role),
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
    user: User = Depends(writer_or_moderator),
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
    user: User = Depends(moderator_only),
):
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
    return {"message": "Route deleted", "id": route_id, "deleted_by": user.username}


@router.get(
    "/routes/{route_id}/incidents",
    response_model=list[IncidentResponse],
)
def route_incidents(
    route_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(any_role),
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
    user: User = Depends(any_role),
):
    del user

    limit = min(max(limit, 1), 200)

    statement = (
        select(IncidentRecord)
        .options(selectinload(IncidentRecord.related_items))
        .order_by(IncidentRecord.id.desc())
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
    user: User = Depends(any_role),
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
    user: User = Depends(writer_or_moderator),
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
    user: User = Depends(writer_or_moderator),
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
    user: User = Depends(moderator_only),
):
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
        "deleted_by": user.username,
    }
