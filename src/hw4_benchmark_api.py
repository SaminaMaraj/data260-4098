from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .hw4_api import incident_response, require_user
from .hw4_database import get_db
from .hw4_models import IncidentRecord, User


router = APIRouter(
    prefix="/api/hw4/benchmark",
    tags=["HW4 N+1 Benchmark"],
)


@router.get("/incidents/naive")
def naive_incidents(
    page_size: int = Query(10, ge=1, le=200),
    page: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    del user

    records = db.scalars(
        select(IncidentRecord)
        .order_by(IncidentRecord.id)
        .offset(page * page_size)
        .limit(page_size)
    ).all()

    return {
        "version": "naive",
        "page": page,
        "page_size": page_size,
        "records": [
            incident_response(record)
            for record in records
        ],
    }


@router.get("/incidents/fixed")
def fixed_incidents(
    page_size: int = Query(10, ge=1, le=200),
    page: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    del user

    records = db.scalars(
        select(IncidentRecord)
        .options(selectinload(IncidentRecord.related_items))
        .order_by(IncidentRecord.id)
        .offset(page * page_size)
        .limit(page_size)
    ).all()

    return {
        "version": "fixed",
        "page": page,
        "page_size": page_size,
        "records": [
            incident_response(record)
            for record in records
        ],
    }