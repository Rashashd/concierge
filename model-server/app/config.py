"""Runtime settings for the lean classifier model-server."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Model-server settings loaded from environment variables."""

    model_config = SettingsConfigDict(extra="forbid")

    log_level: str = "INFO"
    model_server_service_token: SecretStr = SecretStr("")
    verify_artifact_hashes: bool = True


@lru_cache
def get_settings() -> Settings:
    """Return cached model-server settings."""
    return Settings()
