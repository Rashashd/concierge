from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.config import Settings, get_settings
from app.schemas import TenantContext, WidgetTokenRequest, WidgetTokenResponse
from app.security.widget_token import InvalidWidgetTokenError, issue_widget_token

router = APIRouter(prefix="/widget", tags=["widget"])


@router.post("/token", response_model=WidgetTokenResponse)
async def issue_token(
    request: WidgetTokenRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> WidgetTokenResponse:
    if settings.dev_widget_tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Widget tenant lookup is not configured",
        )

    tenant_context = TenantContext(
        tenant_id=settings.dev_widget_tenant_id,
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
