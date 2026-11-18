from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "My World API"
    environment: str = "development"

    database_url: SecretStr
    jwt_secret: SecretStr = Field(min_length=32)
    ip_hash_secret: SecretStr = Field(min_length=32)

    access_token_minutes: int = 15
    refresh_token_days: int = 14
    cookie_secure: bool = True
    cors_origins: list[str] = ["http://localhost:3000"]

    tmdb_api_token: SecretStr | None = None
    catalogue_user_agent: str = "MyWorld/0.1 (+https://github.com/liviakiss/my-world)"

    frontend_url: str = "http://localhost:3000"
    email_provider: Literal["console", "resend"] = "console"
    email_from: str = "My World <onboarding@resend.dev>"
    resend_api_key: SecretStr | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def require_real_email_in_production(self) -> "Settings":
        if self.environment == "production" and self.email_provider != "resend":
            raise ValueError("production must send real email (EMAIL_PROVIDER=resend)")
        if self.email_provider == "resend" and self.resend_api_key is None:
            raise ValueError("RESEND_API_KEY is required when EMAIL_PROVIDER=resend")
        return self


settings = Settings()
