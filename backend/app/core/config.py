from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment or .env."""

    azure_openai_api_key: SecretStr = Field(default=SecretStr(""))
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2025-04-01-preview"
    azure_openai_timeout_seconds: float = 30
    azure_openai_max_retries: int = 2
    widget_token_secret: SecretStr = Field(default=SecretStr(""))

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
