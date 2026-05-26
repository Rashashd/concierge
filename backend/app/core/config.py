"""App settings — vault_addr, vault_token, log_level from env; all else from Vault."""

from functools import lru_cache
from typing import Literal

from pydantic import UUID4, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

_LLM_KEY_FIELDS: dict[str, list[str]] = {
    "openai": ["openai_api_key"],
    "azure": [
        "azure_openai_api_key",
        "azure_openai_endpoint",
        "azure_openai_deployment",
        "azure_openai_embedding_deployment",
    ],
    "groq": ["groq_api_key"],
}


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

    llm_provider: Literal["openai", "azure", "groq"] = "azure"
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

    def validate_fully_loaded(self) -> None:
        """Raise ValueError for blank required secrets after Vault load."""
        errors: list[str] = []

        _required_str = [
            "database_url", "redis_url", "minio_endpoint", "minio_access_key",
        ]
        for field in _required_str:
            if not getattr(self, field):
                errors.append(field)

        _required_secret = [
            "backend_secret_key", "widget_token_secret", "minio_secret_key",
        ]
        for field in _required_secret:
            if not getattr(self, field).get_secret_value():
                errors.append(field)

        for field in _LLM_KEY_FIELDS.get(self.llm_provider, []):
            val = getattr(self, field)
            raw = val.get_secret_value() if isinstance(val, SecretStr) else val
            if not raw:
                errors.append(f"{field} (required for provider={self.llm_provider})")

        if self.langchain_tracing_v2 and not self.langchain_api_key.get_secret_value():
            errors.append("langchain_api_key (required when langchain_tracing_v2=true)")

        if errors:
            raise ValueError(
                "Missing required secrets after Vault load — refusing to start.\n"
                + "\n".join(f"  • {e}" for e in errors)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
