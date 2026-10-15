"""MongoDB document CRUD API for DATA 260 Homework 6 Part 1."""

from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, status
from pymongo.errors import PyMongoError

from .mongo_db import get_incidents_collection
from .mongo_schemas import (
    MongoIncidentCreate,
    MongoIncidentOut,
    MongoIncidentUpdate,
)


router = APIRouter(prefix="/api/mongo/incidents", tags=["HW6 MongoDB Incidents"])


def _object_id(value: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail="Invalid MongoDB id format.")
    return ObjectId(value)


def _serialize(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "incident_title": document.get("incident_title"),
        "route_line": document.get("route_line"),
        "description": document.get("description"),
        "status": document.get("status"),
        "category": document.get("category"),
        "occurred_at": document.get("occurred_at"),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="MongoDB incident not found.")


@router.post("", response_model=MongoIncidentOut, status_code=status.HTTP_201_CREATED)
def create_mongo_incident(payload: MongoIncidentCreate) -> dict:
    document = payload.model_dump()
    timestamp = _now()
    document["created_at"] = timestamp
    document["updated_at"] = timestamp

    try:
        collection = get_incidents_collection()
        result = collection.insert_one(document)
        created = collection.find_one({"_id": result.inserted_id})
        if created is None:
            raise HTTPException(status_code=500, detail="Created document could not be read.")
        return _serialize(created)
    except HTTPException:
        raise
    except PyMongoError as exc:
        if getattr(exc, "code", None) == 11000:
            raise HTTPException(status_code=409, detail="An incident with the same unique value already exists.") from exc
        raise HTTPException(status_code=503, detail=f"MongoDB error while creating incident: {exc}") from exc


@router.get("", response_model=list[MongoIncidentOut])
def list_mongo_incidents() -> list[dict]:
    try:
        documents = get_incidents_collection().find().sort("created_at", -1)
        return [_serialize(document) for document in documents]
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB error while listing incidents: {exc}") from exc


@router.get("/{incident_id}", response_model=MongoIncidentOut)
def get_mongo_incident(incident_id: str) -> dict:
    object_id = _object_id(incident_id)
    try:
        document = get_incidents_collection().find_one({"_id": object_id})
        if document is None:
            raise _not_found()
        return _serialize(document)
    except HTTPException:
        raise
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB error while reading incident: {exc}") from exc


@router.put("/{incident_id}", response_model=MongoIncidentOut)
def update_mongo_incident(incident_id: str, payload: MongoIncidentUpdate) -> dict:
    object_id = _object_id(incident_id)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="At least one field is required for an update.")
    updates["updated_at"] = _now()

    try:
        collection = get_incidents_collection()
        if collection.find_one({"_id": object_id}) is None:
            raise _not_found()
        collection.update_one({"_id": object_id}, {"$set": updates})
        updated = collection.find_one({"_id": object_id})
        if updated is None:
            raise _not_found()
        return _serialize(updated)
    except HTTPException:
        raise
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB error while updating incident: {exc}") from exc


@router.delete("/{incident_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mongo_incident(incident_id: str) -> None:
    object_id = _object_id(incident_id)
    try:
        result = get_incidents_collection().delete_one({"_id": object_id})
        if result.deleted_count == 0:
            raise _not_found()
    except HTTPException:
        raise
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail=f"MongoDB error while deleting incident: {exc}") from exc

