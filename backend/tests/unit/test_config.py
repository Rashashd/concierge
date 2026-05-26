import pytest
from pydantic import SecretStr

from app.core.config import Settings


def _full_settings(**overrides: object) -> Settings:
    base: dict[str, object] = dict(
        vault_addr="http://localhost:8200",
        vault_token=SecretStr("root"),
        database_url="postgresql+asyncpg://u:p@host:5432/db",
        redis_url="redis://localhost:6379",
        minio_endpoint="minio:9000",
        minio_access_key="minioadmin",
        minio_secret_key=SecretStr("miniopassword"),
        backend_secret_key=SecretStr("backend-secret"),
        widget_token_secret=SecretStr("widget-secret"),
        llm_provider="openai",
        openai_api_key=SecretStr("sk-test"),
    )
    base.update(overrides)
    return Settings(**base)


# Passes


def test_validate_fully_loaded_passes_when_all_present() -> None:
    _full_settings().validate_fully_loaded()


# Collects all errors at once


def test_validate_reports_every_missing_field_at_once() -> None:
    settings = _full_settings(
        database_url="",
        redis_url="",
        backend_secret_key=SecretStr(""),
    )
    with pytest.raises(ValueError) as exc_info:
        settings.validate_fully_loaded()
    msg = str(exc_info.value)
    assert "database_url" in msg
    assert "redis_url" in msg
    assert "backend_secret_key" in msg


# Required plain strings


@pytest.mark.parametrize(
    "field",
    ["database_url", "redis_url", "minio_endpoint", "minio_access_key"],
)
def test_validate_fails_on_blank_required_string(field: str) -> None:
    settings = _full_settings(**{field: ""})
    with pytest.raises(ValueError, match=field):
        settings.validate_fully_loaded()


# Required secrets


@pytest.mark.parametrize(
    "field",
    ["backend_secret_key", "widget_token_secret", "minio_secret_key"],
)
def test_validate_fails_on_blank_required_secret(field: str) -> None:
    settings = _full_settings(**{field: SecretStr("")})
    with pytest.raises(ValueError, match=field):
        settings.validate_fully_loaded()


# LLM provider key checks


def test_validate_fails_when_openai_key_is_empty() -> None:
    settings = _full_settings(llm_provider="openai", openai_api_key=SecretStr(""))
    with pytest.raises(ValueError, match="openai_api_key"):
        settings.validate_fully_loaded()


def test_validate_ignores_openai_key_when_provider_is_azure() -> None:
    settings = _full_settings(
        llm_provider="azure",
        openai_api_key=SecretStr(""),
        azure_openai_api_key=SecretStr("azure-key"),
        azure_openai_endpoint="https://my.openai.azure.com",
        azure_openai_deployment="my-deployment",
        azure_openai_embedding_deployment="my-embed",
    )
    settings.validate_fully_loaded()


def test_validate_fails_when_azure_fields_are_missing() -> None:
    settings = _full_settings(
        llm_provider="azure",
        openai_api_key=SecretStr(""),
        azure_openai_api_key=SecretStr(""),
        azure_openai_endpoint="",
        azure_openai_deployment="",
        azure_openai_embedding_deployment="",
    )
    with pytest.raises(ValueError) as exc_info:
        settings.validate_fully_loaded()
    msg = str(exc_info.value)
    assert "azure_openai_api_key" in msg
    assert "azure_openai_endpoint" in msg
    assert "azure_openai_deployment" in msg


def test_validate_fails_when_groq_key_is_empty() -> None:
    settings = _full_settings(
        llm_provider="groq",
        openai_api_key=SecretStr(""),
        groq_api_key=SecretStr(""),
    )
    with pytest.raises(ValueError, match="groq_api_key"):
        settings.validate_fully_loaded()


def test_validate_passes_for_groq_provider_with_key_present() -> None:
    settings = _full_settings(
        llm_provider="groq",
        openai_api_key=SecretStr(""),
        groq_api_key=SecretStr("gsk-test"),
    )
    settings.validate_fully_loaded()


# LangChain tracing


def test_validate_fails_when_tracing_enabled_but_api_key_is_empty() -> None:
    settings = _full_settings(
        langchain_tracing_v2=True,
        langchain_api_key=SecretStr(""),
    )
    with pytest.raises(ValueError, match="langchain_api_key"):
        settings.validate_fully_loaded()


def test_validate_passes_when_tracing_disabled_and_api_key_is_empty() -> None:
    settings = _full_settings(
        langchain_tracing_v2=False,
        langchain_api_key=SecretStr(""),
    )
    settings.validate_fully_loaded()
