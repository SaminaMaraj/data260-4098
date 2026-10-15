"""Pydantic request and response schemas for HW6 MongoDB incidents."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


IncidentStatus = Literal["open", "investigating", "resolved"]
IncidentCategory = Literal[
    "delay",
    "collision",
    "service-suspension",
    "infrastructure-issue",
]


class MongoIncidentCreate(BaseModel):
    incident_title: str = Field(..., min_length=1, max_length=100)
    route_line: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    status: IncidentStatus = "open"
    category: IncidentCategory
    occurred_at: datetime


class MongoIncidentUpdate(BaseModel):
    incident_title: str | None = Field(default=None, min_length=1, max_length=100)
    route_line: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    status: IncidentStatus | None = None
    category: IncidentCategory | None = None
    occurred_at: datetime | None = None


class MongoIncidentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    incident_title: str
    route_line: str
    description: str | None = None
    status: IncidentStatus
    category: IncidentCategory
    occurred_at: datetime
    created_at: datetime
    updated_at: datetime

