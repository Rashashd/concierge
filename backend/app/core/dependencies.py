"""Shared Depends() functions: sessions, auth, role guards, singletons."""

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

import redis.asyncio as aioredis
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.schemas import TenantContext, UserContext
from app.security.widget_token import InvalidWidgetTokenError, verify_widget_token

logger = structlog.get_logger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


# Database


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """No-RLS session for auth and manager routes."""
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


# Widget auth


async def get_current_tenant(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
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
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserContext:
    """Verify the user JWT and return the user context."""
    import jwt

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization token",
        )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.backend_secret_key.get_secret_value(),
            algorithms=["HS256"],
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    return UserContext(
        user_id=uuid.UUID(user_id),
        role=payload["role"],
        tenant_id=uuid.UUID(payload["tenant_id"]) if payload.get("tenant_id") else None,
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


def get_http_client(request: Request) -> object:
    return request.app.state.http_client


def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis


def get_llm_client(request: Request) -> object:
    return request.app.state.llm
