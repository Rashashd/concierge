"""Startup and shutdown: initialise Vault, DB engine, Redis, and httpx pool."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

import httpx
import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.infra.llm import get_embeddings, get_llm
from app.infra.vault import create_vault_client
from app.security.redaction import build_redactor

logger = structlog.get_logger(__name__)


_LLMProvider = Literal["openai", "azure", "groq"]
_VALID_PROVIDERS: tuple[str, ...] = ("openai", "azure", "groq")


def _detect_llm_provider(llm_config: dict[str, str]) -> _LLMProvider:
    """Infer provider from whichever API key is present in the Vault secret."""
    has_azure = bool(
        llm_config.get("azure_openai_api_key")
        and llm_config.get("azure_openai_endpoint")
    )
    if has_azure:
        return "azure"
    if llm_config.get("openai_api_key"):
        return "openai"
    if llm_config.get("groq_api_key"):
        return "groq"
    raise RuntimeError(
        "secret/concierge/llm has no 'provider' key and no recognizable API keys"
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()

    # Vault
    vault = create_vault_client(
        addr=settings.vault_addr, token=settings.vault_token.get_secret_value()
    )
    app.state.vault = vault

    settings.database_url = vault.get_database_url()
    settings.redis_url = vault.get_redis_url()

    llm_config = vault.get_llm_config()
    _raw_provider = llm_config.get("provider") or _detect_llm_provider(llm_config)
    if _raw_provider not in _VALID_PROVIDERS:
        raise RuntimeError(f"Unsupported LLM provider '{_raw_provider}' in Vault")
    settings.llm_provider = _raw_provider  # type: ignore[assignment]
    settings.openai_api_key = SecretStr(llm_config.get("openai_api_key", ""))
    settings.openai_model = llm_config.get("openai_model", "gpt-4o-mini")
    settings.openai_embedding_model = llm_config.get(
        "openai_embedding_model", "text-embedding-3-small"
    )
    settings.azure_openai_api_key = SecretStr(
        llm_config.get("azure_openai_api_key", "")
    )
    settings.azure_openai_endpoint = llm_config.get("azure_openai_endpoint", "")
    settings.azure_openai_deployment = llm_config.get("azure_openai_deployment", "")
    settings.azure_openai_embedding_deployment = llm_config.get(
        "azure_openai_embedding_deployment", ""
    )
    settings.groq_api_key = SecretStr(llm_config.get("groq_api_key", ""))
    app.state.llm = get_llm(settings)
    app.state.embeddings = get_embeddings(settings)

    minio_config = vault.get_minio_config()
    settings.minio_endpoint = minio_config["endpoint"]
    settings.minio_access_key = minio_config["access_key"]
    settings.minio_secret_key = SecretStr(minio_config["secret_key"])

    settings.backend_secret_key = SecretStr(vault.get_backend_secret_key())
    settings.widget_token_secret = SecretStr(vault.get_widget_secret())
    settings.model_server_token = SecretStr(vault.get_service_token("model_server"))
    settings.guardrails_token = SecretStr(vault.get_service_token("guardrails"))

    langchain_config = vault.get_langchain_config()
    settings.langchain_tracing_v2 = (
        langchain_config.get("tracing_enabled", "false").lower() == "true"
    )
    settings.langchain_api_key = SecretStr(langchain_config.get("api_key", ""))
    settings.langchain_project = langchain_config.get("project", "concierge")

    settings.validate_fully_loaded()
    logger.info("settings.validated")

    # Database
    engine = create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.engine = engine
    app.state.session_factory = session_factory

    # fail fast if DB is unreachable
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("database.connected")

    # Redis
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    await redis_client.ping()
    app.state.redis = redis_client
    logger.info("redis.connected")

    # HTTP client
    http_client = httpx.AsyncClient(timeout=30.0)
    app.state.http_client = http_client

    # Redactor (loads spaCy model — CPU-bound, run off the event loop)
    app.state.redactor = await asyncio.to_thread(build_redactor)
    logger.info("redactor.ready")

    logger.info("backend.started")

    try:
        yield
    finally:
        await http_client.aclose()
        await redis_client.aclose()
        await engine.dispose()
        logger.info("backend.stopped")
