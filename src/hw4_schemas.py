from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


ROUTE_CODE_PATTERN = r"^RT-\d{3,}$"
INCIDENT_CODE_PATTERN = r"^INC-\d{6}$"


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: int
    name: str
    email: EmailStr


class IncidentCreate(BaseModel):
    incidentCode: str = Field(pattern=INCIDENT_CODE_PATTERN)
    incidentTitle: str = Field(min_length=3, max_length=100)
    routeLine: str = Field(min_length=2, max_length=100)
    routeId: int | None = Field(default=None, ge=1)
    submitterEmail: EmailStr
    description: str = Field(min_length=26, max_length=1000)
    category: str
    passengersAffected: int = Field(default=0, ge=0)
    termsAccepted: bool = True


class IncidentUpdate(BaseModel):
    incidentCode: str = Field(pattern=INCIDENT_CODE_PATTERN)
    incidentTitle: str = Field(min_length=3, max_length=100)
    routeLine: str = Field(min_length=2, max_length=100)
    routeId: int | None = Field(default=None, ge=1)
    submitterEmail: EmailStr
    description: str = Field(min_length=26, max_length=1000)
    category: str
    passengersAffected: int = Field(default=0, ge=0)
    termsAccepted: bool = True


class RelatedDataResponse(BaseModel):
    id: int
    related_type: str
    related_text: str


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    incidentCode: str
    incidentTitle: str
    routeLine: str
    routeId: int
    submitterEmail: EmailStr
    description: str
    category: str
    passengersAffected: int
    termsAccepted: bool
    submissionDate: str
    createdAt: datetime
    updatedAt: datetime
    related: list[RelatedDataResponse] = []


class RouteCreate(BaseModel):
    routeName: str = Field(min_length=2, max_length=100)
    operator: str = Field(min_length=2, max_length=100)
    routeCode: str = Field(pattern=ROUTE_CODE_PATTERN)


class RouteUpdate(RouteCreate):
    pass


class RouteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    routeName: str
    operator: str
    routeCode: str
    createdAt: datetime
    updatedAt: datetime
