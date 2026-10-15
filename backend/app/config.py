from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    app_name: str = "My World API"      
    environment: str = "development"    
    database_url: SecretStr
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()