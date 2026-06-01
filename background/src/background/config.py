from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BACKGROUND_")

    service_name: str = "email-delivery-manager-background"
    environment: str = "local"
    job_timeout_seconds: float = 30.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
