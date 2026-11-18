from pydantic import BaseModel, ConfigDict, Field


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
