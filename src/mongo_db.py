"""Lazy PyMongo connection and MongoDB collection validation."""

from __future__ import annotations

from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from .mongo_config import MONGO_DB_NAME, MONGO_INCIDENTS_COLLECTION, MONGO_URI


_client: MongoClient | None = None
_schema_initialized = False


def get_mongo_client() -> MongoClient:
    """Return one reusable client without connecting during app import."""
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    return _client


def get_mongo_db() -> Database:
    return get_mongo_client()[MONGO_DB_NAME]


def _incident_validator() -> dict:
    """MongoDB-side validation that mirrors the Pydantic API schema."""
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "required": [
                "incident_title",
                "route_line",
                "status",
                "category",
                "occurred_at",
                "created_at",
                "updated_at",
            ],
            "properties": {
                "incident_title": {"bsonType": "string", "maxLength": 100},
                "route_line": {"bsonType": "string", "maxLength": 100},
                "description": {"bsonType": ["string", "null"], "maxLength": 2000},
                "status": {
                    "enum": ["open", "investigating", "resolved"],
                },
                "category": {
                    "enum": [
                        "delay",
                        "collision",
                        "service-suspension",
                        "infrastructure-issue",
                    ],
                },
                "occurred_at": {"bsonType": "date"},
                "created_at": {"bsonType": "date"},
                "updated_at": {"bsonType": "date"},
            },
        }
    }


def get_incidents_collection() -> Collection:
    """Return the validated HW6 document collection."""
    global _schema_initialized
    db = get_mongo_db()

    if not _schema_initialized:
        collection_names = db.list_collection_names()
        if MONGO_INCIDENTS_COLLECTION not in collection_names:
            db.create_collection(
                MONGO_INCIDENTS_COLLECTION,
                validator=_incident_validator(),
                validationLevel="strict",
                validationAction="error",
            )
        else:
            db.command(
                "collMod",
                MONGO_INCIDENTS_COLLECTION,
                validator=_incident_validator(),
                validationLevel="strict",
                validationAction="error",
            )
        _schema_initialized = True

    return db[MONGO_INCIDENTS_COLLECTION]


def get_messages_collection() -> Collection:
    return get_mongo_db()["messages"]


def get_summaries_collection() -> Collection:
    return get_mongo_db()["summaries"]


def get_episodes_collection() -> Collection:
    return get_mongo_db()["episodes"]

