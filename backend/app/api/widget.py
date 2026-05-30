import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.dependencies import get_session, require_tenant_admin
from app.repositories import widget_configs as widget_config_repo
from app.schemas import (
    TenantContext,
    UserContext,
    WidgetConfigCreate,
    WidgetConfigPublic,
    WidgetTokenRequest,
    WidgetTokenResponse,
)
from app.security.widget_token import InvalidWidgetTokenError, issue_widget_token
from app.services import widget_configs as widget_service

router = APIRouter(prefix="/widget", tags=["widget"])


@router.get("/config", response_model=WidgetConfigPublic)
async def get_widget_config(
    widget_id: Annotated[uuid.UUID, Query()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WidgetConfigPublic:
    config = await widget_config_repo.get_by_widget_id(session, widget_id)
    if config is None:
        return WidgetConfigPublic(
            widget_id=widget_id,
            greeting="Hi, how can I help you?",
            theme_color="#0066CC",
        )
    return WidgetConfigPublic(
        widget_id=config.widget_id,
        greeting=config.greeting,
        theme_color=config.theme_color,
    )


@router.post(
    "/config", response_model=WidgetConfigPublic, status_code=status.HTTP_201_CREATED
)
async def create_or_update_widget_config(
    body: WidgetConfigCreate,
    user: Annotated[UserContext, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WidgetConfigPublic:
    if user.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tenant")
    config = await widget_service.upsert_widget_config(
        session,
        tenant_id=user.tenant_id,
        greeting=body.greeting,
        theme_color=body.theme_color,
        enabled_tools=body.enabled_tools,
    )
    return WidgetConfigPublic(
        widget_id=config.widget_id,
        greeting=config.greeting,
        theme_color=config.theme_color,
    )


@router.post("/token", response_model=WidgetTokenResponse)
async def issue_token(
    request: WidgetTokenRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> WidgetTokenResponse:
    resolved_tenant_id = await widget_service.resolve_widget_tenant(
        session, request.widget_id
    )
    tenant_context = TenantContext(
        tenant_id=resolved_tenant_id,
        widget_id=request.widget_id,
        session_id=request.session_id,
    )
    try:
        token = issue_widget_token(
            tenant_context=tenant_context,
            secret=settings.widget_token_secret.get_secret_value(),
            expires_in_seconds=settings.widget_token_ttl_seconds,
        )
    except InvalidWidgetTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Widget token signing is not configured",
        ) from exc
    return WidgetTokenResponse(
        access_token=token,
        expires_in=settings.widget_token_ttl_seconds,
    )
