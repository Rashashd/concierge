from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from app.api.widget import issue_token
from app.core.config import Settings
from app.schemas import TenantContext, WidgetTokenRequest
from app.security.widget_token import issue_widget_token, verify_widget_token

TEST_SECRET = "0123456789abcdef0123456789abcdef"
VAULT_DEFAULTS = {
    "vault_addr": "http://localhost:8200",
    "vault_token": SecretStr("root"),
}


def test_issue_widget_token_round_trips_to_tenant_context() -> None:
    tenant_context = TenantContext(
        tenant_id=uuid4(),
        widget_id=uuid4(),
        session_id="session-1",
    )

    token = issue_widget_token(
        tenant_context=tenant_context,
        secret=TEST_SECRET,
        expires_in_seconds=900,
    )

    assert verify_widget_token(token, TEST_SECRET) == tenant_context


def test_widget_token_request_rejects_tenant_id() -> None:
    with pytest.raises(ValidationError):
        WidgetTokenRequest.model_validate(
            {
                "widget_id": str(uuid4()),
                "session_id": "session-1",
                "tenant_id": str(uuid4()),
            }
        )


@pytest.mark.asyncio
async def test_widget_token_endpoint_uses_resolved_tenant_id() -> None:
    tenant_id = uuid4()
    widget_id = uuid4()
    settings = Settings(
        **VAULT_DEFAULTS,
        widget_token_secret=SecretStr(TEST_SECRET),
    )

    with patch(
        "app.api.widget.widget_service.resolve_widget_tenant",
        AsyncMock(return_value=tenant_id),
    ):
        response = await issue_token(
            request=WidgetTokenRequest(widget_id=widget_id, session_id="session-1"),
            settings=settings,
            session=AsyncMock(),
        )

    tenant_context = verify_widget_token(response.access_token, TEST_SECRET)
    assert tenant_context.tenant_id == tenant_id
    assert tenant_context.widget_id == widget_id
    assert tenant_context.session_id == "session-1"


@pytest.mark.asyncio
async def test_widget_token_endpoint_falls_back_to_widget_id_when_no_config() -> None:
    widget_id = uuid4()
    settings = Settings(
        **VAULT_DEFAULTS,
        widget_token_secret=SecretStr(TEST_SECRET),
    )

    with patch(
        "app.api.widget.widget_service.resolve_widget_tenant",
        AsyncMock(return_value=widget_id),  # fallback: no config found
    ):
        response = await issue_token(
            request=WidgetTokenRequest(widget_id=widget_id, session_id="session-1"),
            settings=settings,
            session=AsyncMock(),
        )

    tenant_context = verify_widget_token(response.access_token, TEST_SECRET)
    assert tenant_context.tenant_id == widget_id
