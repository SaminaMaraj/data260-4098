from pydantic import BaseModel, EmailStr, Field


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
    incidentTitle: str = Field(min_length=3, max_length=100)
    routeLine: str = Field(min_length=2, max_length=100)
    submitterEmail: EmailStr
    description: str = Field(min_length=26, max_length=1000)
    category: str
    termsAccepted: bool = True


class IncidentUpdate(BaseModel):
    incidentTitle: str = Field(min_length=3, max_length=100)
    routeLine: str = Field(min_length=2, max_length=100)
    submitterEmail: EmailStr
    description: str = Field(min_length=26, max_length=1000)
    category: str
    termsAccepted: bool = True


class RelatedDataResponse(BaseModel):
    id: int
    related_type: str
    related_text: str


class IncidentResponse(BaseModel):
    id: int
    incidentTitle: str
    routeLine: str
    submitterEmail: EmailStr
    description: str
    category: str
    termsAccepted: bool
    submissionDate: str
    related: list[RelatedDataResponse] = []