from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings, get_settings
from app.schemas import TenantContext
from app.security.widget_token import InvalidWidgetTokenError, verify_widget_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_llm_client(request: Request) -> object:
    return request.app.state.llm


async def get_current_tenant(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TenantContext:
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
