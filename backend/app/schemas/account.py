from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.auth import PASSWORD_MAX_LENGTH


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=100)


class NotificationSettings(BaseModel):
    email_enabled: bool
    day_before: bool


class NotificationSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_enabled: bool | None = None
    day_before: bool | None = None


class ChangeEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    new_email: EmailStr

    @field_validator("new_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ConfirmEmailChangeRequest(VerifyEmailRequest):
    pass


class DeleteAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
