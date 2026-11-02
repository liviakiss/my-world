import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import UserRole

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128


class EmailNormalizingModel(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class SignupRequest(EmailNormalizingModel):
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class LoginRequest(EmailNormalizingModel):
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class MessageResponse(BaseModel):
    message: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    is_email_verified: bool
    created_at: datetime
