from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.schemas import UserContext


def _make_admin_context() -> UserContext:
    return UserContext(
        user_id=uuid4(),
        role="tenant_admin",
        tenant_id=uuid4(),
    )


@pytest.mark.asyncio
async def test_list_escalations_requires_tenant_admin() -> None:
    manager = UserContext(user_id=uuid4(), role="tenant_manager", tenant_id=None)
    from app.core.dependencies import require_tenant_admin

    with pytest.raises(HTTPException) as exc_info:
        require_tenant_admin(manager)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_escalations_returns_tenant_escalations() -> None:
    admin = _make_admin_context()
    log_id = uuid4()
    _dt = type("_dt", (), {"isoformat": lambda s: "2025-01-01T00:00:00"})

    async def fake_list(session, *, tenant_id, limit=100) -> list[object]:
        return [
            type(
                "FakeLog",
                (),
                {
                    "id": log_id,
                    "tenant_id": admin.tenant_id,
                    "payload": {
                        "conversation_id": "conv-abc",
                        "reason": "Needs a human",
                    },
                    "created_at": _dt(),
                },
            )()
        ]

    from app.api.escalations import router

    with (
        patch(
            "app.api.escalations.audit_repo.list_escalations_by_tenant",
            side_effect=fake_list,
        ),
        patch(
            "app.api.escalations.get_admin_tenant_session",
            AsyncMock(return_value=AsyncMock()),
        ),
    ):
        coro = router.routes[0].endpoint  # type: ignore[attr-defined]
        result = await coro(user=admin, session=AsyncMock())

    assert len(result) == 1
    assert result[0].id == log_id
    assert result[0].conversation_id == "conv-abc"
    assert result[0].reason == "Needs a human"


@pytest.mark.asyncio
async def test_list_escalations_returns_empty_when_none() -> None:
    admin = _make_admin_context()

    async def fake_list(session, *, tenant_id, limit=100) -> list[object]:
        return []

    from app.api.escalations import router

    with patch(
        "app.api.escalations.audit_repo.list_escalations_by_tenant",
        side_effect=fake_list,
    ):
        coro = router.routes[0].endpoint  # type: ignore[attr-defined]
        result = await coro(user=admin, session=AsyncMock())

    assert result == []
