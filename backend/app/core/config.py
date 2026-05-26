"""App settings — vault_addr, vault_token, log_level from env; all else from Vault."""

from functools import lru_cache
from typing import Literal

from pydantic import UUID4, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        extra="forbid",
    )

    # Environment
    vault_addr: str
    vault_token: SecretStr
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Vault
    database_url: str = ""
    redis_url: str = ""

    llm_provider: Literal["openai", "azure", "groq"] = "openai"
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    azure_openai_api_key: SecretStr = SecretStr("")
    azure_openai_endpoint: str = ""
    azure_openai_deployment: str = ""
    azure_openai_embedding_deployment: str = ""
    azure_openai_api_version: str = "2025-04-01-preview"
    azure_openai_timeout_seconds: float = 30.0
    azure_openai_max_retries: int = 2

    groq_api_key: SecretStr = SecretStr("")

    minio_endpoint: str = ""
    minio_access_key: str = ""
    minio_secret_key: SecretStr = SecretStr("")
    minio_bucket: str = "concierge"

    backend_secret_key: SecretStr = SecretStr("")
    widget_token_secret: SecretStr = SecretStr("")
    widget_token_ttl_seconds: int = 900

    # skips token-exchange in local dev
    dev_widget_tenant_id: UUID4 | None = None

    model_server_url: str = "http://model-server:8001"
    model_server_token: SecretStr = SecretStr("")
    guardrails_url: str = "http://guardrails:8002"
    guardrails_token: SecretStr = SecretStr("")

    langchain_tracing_v2: bool = False
    langchain_api_key: SecretStr = SecretStr("")
    langchain_project: str = "concierge"


@lru_cache
def get_settings() -> Settings:
    return Settings()
