"""Unit tests for the tenants service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.tenants import full_delete_tenant, get_audit_log_with_emails


def _mock_session() -> MagicMock:
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=None)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.begin.return_value = ctx
    return session


def _fake_entry(actor_id=None) -> MagicMock:
    entry = MagicMock()
    entry.id = uuid4()
    entry.actor_id = actor_id or uuid4()
    entry.actor_role = "tenant_admin"
    entry.tenant_id = uuid4()
    entry.action = "content.created"
    entry.payload = {}
    entry.created_at = datetime(2025, 1, 1, tzinfo=UTC)
    return entry


# get_audit_log_with_emails


@pytest.mark.asyncio
async def test_get_audit_log_with_emails_pairs_entries_with_emails(monkeypatch) -> None:
    actor_id = uuid4()
    entry = _fake_entry(actor_id)
    monkeypatch.setattr(
        "app.services.tenants.audit_repo.list_all", AsyncMock(return_value=[entry])
    )
    monkeypatch.setattr(
        "app.services.tenants.user_repo.get_emails_by_ids",
        AsyncMock(return_value={actor_id: "actor@example.com"}),
    )

    result = await get_audit_log_with_emails(MagicMock(), limit=10)

    assert len(result) == 1
    assert result[0][0] is entry
    assert result[0][1] == "actor@example.com"


@pytest.mark.asyncio
async def test_get_audit_log_with_emails_uses_none_for_unknown_actor(
    monkeypatch,
) -> None:
    entry = _fake_entry()
    monkeypatch.setattr(
        "app.services.tenants.audit_repo.list_all", AsyncMock(return_value=[entry])
    )
    monkeypatch.setattr(
        "app.services.tenants.user_repo.get_emails_by_ids",
        AsyncMock(return_value={}),
    )

    result = await get_audit_log_with_emails(MagicMock())

    assert result[0][1] is None


@pytest.mark.asyncio
async def test_get_audit_log_with_emails_returns_empty_list(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.tenants.audit_repo.list_all", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "app.services.tenants.user_repo.get_emails_by_ids", AsyncMock(return_value={})
    )

    result = await get_audit_log_with_emails(MagicMock())

    assert result == []


# full_delete_tenant


@pytest.mark.asyncio
async def test_full_delete_tenant_calls_erase_then_deletes_users_and_tenant(
    monkeypatch,
) -> None:
    tenant_id = uuid4()
    erase_mock = AsyncMock()
    delete_users_mock = AsyncMock()
    delete_tenant_mock = AsyncMock()
    monkeypatch.setattr("app.services.tenants.erase_tenant", erase_mock)
    monkeypatch.setattr(
        "app.services.tenants.user_repo.delete_by_tenant", delete_users_mock
    )
    monkeypatch.setattr("app.services.tenants.tenant_repo.delete", delete_tenant_mock)

    await full_delete_tenant(
        tenant_id=tenant_id,
        actor_id=uuid4(),
        actor_role="tenant_manager",
        session=_mock_session(),
        redis=AsyncMock(),
        minio=MagicMock(),
    )

    erase_mock.assert_awaited_once()
    delete_users_mock.assert_awaited_once()
    delete_tenant_mock.assert_awaited_once()
    assert delete_tenant_mock.call_args.args[1] == tenant_id


@pytest.mark.asyncio
async def test_full_delete_tenant_passes_correct_args_to_erase(monkeypatch) -> None:
    tenant_id = uuid4()
    actor_id = uuid4()
    erase_mock = AsyncMock()
    monkeypatch.setattr("app.services.tenants.erase_tenant", erase_mock)
    monkeypatch.setattr("app.services.tenants.user_repo.delete_by_tenant", AsyncMock())
    monkeypatch.setattr("app.services.tenants.tenant_repo.delete", AsyncMock())

    await full_delete_tenant(
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_role="tenant_manager",
        session=_mock_session(),
        redis=AsyncMock(),
        minio=MagicMock(),
    )

    kwargs = erase_mock.call_args.kwargs
    assert kwargs["tenant_id"] == tenant_id
    assert kwargs["actor_id"] == actor_id
    assert kwargs["actor_role"] == "tenant_manager"
