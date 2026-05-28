"""Shared Depends() functions: sessions, auth, role guards, singletons."""

from collections.abc import AsyncGenerator
from typing import Annotated

import httpx
import redis.asyncio as aioredis
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings, ChatOpenAI, OpenAIEmbeddings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import User as UserORM
from app.db.user_manager import fastapi_users
from app.infra.guardrails import GuardrailsClient
from app.infra.minio import MinioClient
from app.infra.model_server import ModelServerClient
from app.schemas import TenantContext, UserContext
from app.security.redaction import Redactor
from app.security.widget_token import InvalidWidgetTokenError, verify_widget_token
from app.services.classifier_router import ClassifierClient
from app.services.reranker import Reranker

logger = structlog.get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

# fastapi-users dependency — verifies JWT + fetches User row from DB
_current_active_user = fastapi_users.current_user(active=True)


# Database


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """No-RLS session for auth and manager routes."""
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


# Widget auth


async def get_current_tenant(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TenantContext:
    """Verify the widget JWT and return the tenant context."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing widget token",
        )
    try:
        return verify_widget_token(
            token=credentials.credentials,
            secret=settings.widget_token_secret.get_secret_value(),
        )
    except InvalidWidgetTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid widget token",
        ) from exc


# User auth


async def get_current_user(
    user: Annotated[UserORM, Depends(_current_active_user)],
) -> UserContext:
    """Verify JWT via fastapi-users, fetch User from DB, return UserContext."""
    return UserContext.model_validate(
        {"user_id": user.id, "role": user.role, "tenant_id": user.tenant_id}
    )


# RLS sessions


async def get_tenant_session(
    request: Request,
    tenant: Annotated[TenantContext, Depends(get_current_tenant)],
) -> AsyncGenerator[AsyncSession, None]:
    """Session with RLS set for the current tenant. Use for widget/chat routes."""
    factory = request.app.state.session_factory
    async with factory() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(tenant.tenant_id)},
            )
            yield session


async def get_admin_tenant_session(
    request: Request,
    user: Annotated[UserContext, Depends(get_current_user)],
) -> AsyncGenerator[AsyncSession, None]:
    """Session with RLS for Tenant Admin dashboard routes, sourced from user JWT."""
    if user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires a tenant-scoped account",
        )
    factory = request.app.state.session_factory
    async with factory() as session:
        async with session.begin():
            await session.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(user.tenant_id)},
            )
            yield session


# Role guards


def require_tenant_manager(
    user: Annotated[UserContext, Depends(get_current_user)],
) -> UserContext:
    if user.role != "tenant_manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role"
        )
    return user


def require_tenant_admin(
    user: Annotated[UserContext, Depends(get_current_user)],
) -> UserContext:
    if user.role != "tenant_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role"
        )
    return user


# Singletons


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client  # type: ignore[no-any-return]


def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


def get_llm_client(request: Request) -> ChatOpenAI | AzureChatOpenAI:
    return request.app.state.llm  # type: ignore[no-any-return]


def get_embeddings_client(request: Request) -> AzureOpenAIEmbeddings | OpenAIEmbeddings:
    return request.app.state.embeddings  # type: ignore[no-any-return]


def get_reranker(request: Request) -> Reranker:
    return request.app.state.reranker


def get_minio(request: Request) -> MinioClient:
    return request.app.state.minio  # type: ignore[no-any-return]


def get_redactor(request: Request) -> Redactor:
    return request.app.state.redactor


def get_classifier_client(request: Request) -> ClassifierClient | None:
    return request.app.state.classifier_client  # type: ignore[no-any-return]


def get_guardrails_client(request: Request) -> GuardrailsClient:
    return request.app.state.guardrails_client  # type: ignore[no-any-return]
