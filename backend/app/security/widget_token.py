from uuid import UUID

import jwt
from jwt import InvalidTokenError
from pydantic import ValidationError

from app.schemas import TenantContext


class InvalidWidgetTokenError(ValueError):
    """Raised when the widget JWT is missing required trusted context."""


def verify_widget_token(token: str, secret: str) -> TenantContext:
    if not secret:
        raise InvalidWidgetTokenError("Widget token secret is not configured")

    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return TenantContext(
            tenant_id=UUID(str(payload["tenant_id"])),
            widget_id=UUID(str(payload["widget_id"])),
            session_id=str(payload["session_id"]),
        )
    except (InvalidTokenError, KeyError, TypeError, ValueError, ValidationError) as exc:
        raise InvalidWidgetTokenError("Invalid widget token") from exc
