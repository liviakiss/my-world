from pydantic import Field, SecretStr
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = Settings()
