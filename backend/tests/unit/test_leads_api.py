from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.leads import router
from app.main import create_app
from app.schemas import LeadStatusUpdate, UserContext


def _make_admin_context() -> UserContext:
    return UserContext(
        user_id=uuid4(),
        role="tenant_admin",
        tenant_id=uuid4(),
    )


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


@pytest.mark.asyncio
async def test_list_leads_requires_tenant_admin() -> None:
    user = UserContext(user_id=uuid4(), role="tenant_manager", tenant_id=None)

    from app.core.dependencies import require_tenant_admin

    with pytest.raises(HTTPException) as exc_info:
        require_tenant_admin(user)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_list_leads_filters_by_user_tenant() -> None:
    admin = _make_admin_context()
    lead_id = uuid4()
    dt = type("dt", (), {"isoformat": lambda s: "2025-01-01T00:00:00"})

    async def fake_list_by_tenant(*, session, tenant_id) -> list[object]:
        return [
            type(
                "FakeLead",
                (),
                {
                    "id": lead_id,
                    "tenant_id": admin.tenant_id,
                    "session_id": "session-1",
                    "visitor_name": "Jane",
                    "contact": "jane@example.com",
                    "intent": "Interest",
                    "status": "new",
                    "created_at": dt(),
                },
            )()
        ]

    with patch(
        "app.api.leads.lead_repo.list_by_tenant",
        side_effect=fake_list_by_tenant,
    ), patch(
        "app.api.leads.get_admin_tenant_session",
        AsyncMock(return_value=AsyncMock()),
    ):
        coro = router.routes[0].endpoint  # type: ignore[attr-defined]
        result = await coro(
            user=admin,
            session=AsyncMock(),
        )
        assert len(result) == 1
        assert result[0].id == lead_id
        assert result[0].status == "new"


@pytest.mark.asyncio
async def test_patch_lead_updates_status() -> None:
    admin = _make_admin_context()
    lead_id = uuid4()
    dt = type("dt", (), {"isoformat": lambda s: "2025-01-01T00:00:00"})

    async def fake_update_status(
        *, session, tenant_id, lead_id, status
    ) -> object:
        return type(
            "FakeLead",
            (),
            {
                "id": lead_id,
                "tenant_id": admin.tenant_id,
                "session_id": "session-1",
                "visitor_name": "Jane",
                "contact": "jane@example.com",
                "intent": "Interest",
                "status": status,
                "created_at": dt(),
            },
        )()

    with patch(
        "app.api.leads.lead_repo.update_status",
        side_effect=fake_update_status,
    ), patch(
        "app.api.leads.get_admin_tenant_session",
        AsyncMock(return_value=AsyncMock()),
    ):
        body = LeadStatusUpdate(status="contacted")
        coro = router.routes[1].endpoint  # type: ignore[attr-defined]
        result = await coro(
            lead_id=lead_id,
            body=body,
            user=admin,
            session=AsyncMock(),
        )
        assert result.status == "contacted"


@pytest.mark.asyncio
async def test_patch_lead_returns_404_when_not_found() -> None:
    admin = _make_admin_context()

    async def fake_update_status(*, session, tenant_id, lead_id, status) -> None:
        return None

    with patch(
        "app.api.leads.lead_repo.update_status",
        side_effect=fake_update_status,
    ), patch(
        "app.api.leads.get_admin_tenant_session",
        AsyncMock(return_value=AsyncMock()),
    ):
        body = LeadStatusUpdate(status="contacted")
        coro = router.routes[1].endpoint  # type: ignore[attr-defined]
        with pytest.raises(HTTPException) as exc_info:
            await coro(
                lead_id=uuid4(),
                body=body,
                user=admin,
                session=AsyncMock(),
            )
        assert exc_info.value.status_code == 404
