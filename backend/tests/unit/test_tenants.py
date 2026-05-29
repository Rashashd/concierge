"""Unit tests for /tenants endpoints."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.tenants import create_tenant, list_tenants, suspend_tenant
from app.db.models import Tenant
from app.schemas import TenantCreate, UserContext


def _manager() -> UserContext:
    return UserContext(user_id=uuid4(), role="tenant_manager", tenant_id=None)


def _mock_session() -> MagicMock:
    """Session mock that supports async with session.begin()."""
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=None)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.begin.return_value = ctx
    return session


def _tenant(name: str = "Acme", slug: str = "acme") -> Tenant:
    return Tenant(
        id=uuid4(),
        name=name,
        slug=slug,
        is_active=True,
        llm_persona="",
        guardrail_config={},
        allowed_origins=[],
    )


# create_tenant


@pytest.mark.asyncio
async def test_create_tenant_returns_created_tenant(monkeypatch) -> None:
    t = _tenant()
    monkeypatch.setattr(
        "app.api.tenants.tenant_repo.get_by_slug",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.api.tenants.tenant_repo.create",
        AsyncMock(return_value=t),
    )
    monkeypatch.setattr(
        "app.api.tenants.audit_repo.create",
        AsyncMock(return_value=object()),
    )

    result = await create_tenant(
        TenantCreate(name="Acme", slug="acme"),
        _manager(),
        _mock_session(),
    )

    assert result.slug == "acme"
    assert result.is_active is True


@pytest.mark.asyncio
async def test_create_tenant_raises_409_on_duplicate_slug(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.tenants.tenant_repo.get_by_slug",
        AsyncMock(return_value=_tenant()),
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_tenant(
            TenantCreate(name="Acme", slug="acme"),
            _manager(),
            _mock_session(),
        )

    assert exc_info.value.status_code == 409


# list_tenants


@pytest.mark.asyncio
async def test_list_tenants_returns_all_tenants(monkeypatch) -> None:
    tenants = [_tenant("Alpha", "alpha"), _tenant("Beta", "beta")]
    monkeypatch.setattr(
        "app.api.tenants.tenant_repo.list_all",
        AsyncMock(return_value=tenants),
    )

    result = await list_tenants(_manager(), _mock_session())

    assert len(result) == 2
    assert result[0].slug == "alpha"
    assert result[1].slug == "beta"


@pytest.mark.asyncio
async def test_list_tenants_returns_empty_list(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.tenants.tenant_repo.list_all",
        AsyncMock(return_value=[]),
    )

    result = await list_tenants(_manager(), _mock_session())

    assert result == []


# suspend_tenant


@pytest.mark.asyncio
async def test_suspend_tenant_returns_suspended_tenant(monkeypatch) -> None:
    t = _tenant()
    t.is_active = False
    monkeypatch.setattr(
        "app.api.tenants.tenant_repo.suspend",
        AsyncMock(return_value=t),
    )

    result = await suspend_tenant(t.id, _manager(), _mock_session())

    assert result.is_active is False


@pytest.mark.asyncio
async def test_suspend_tenant_raises_404_when_not_found(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.tenants.tenant_repo.suspend",
        AsyncMock(return_value=None),
    )

    with pytest.raises(HTTPException) as exc_info:
        await suspend_tenant(uuid4(), _manager(), _mock_session())

    assert exc_info.value.status_code == 404
