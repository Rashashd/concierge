"""Unit tests for the /tenants/audit endpoint."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.audit_log import list_audit_log
from app.schemas import UserContext


def _manager() -> UserContext:
    return UserContext(user_id=uuid4(), role="tenant_manager", tenant_id=None)


def _fake_entry(actor_id=None):
    return type(
        "Entry",
        (),
        {
            "id": uuid4(),
            "actor_id": actor_id or uuid4(),
            "actor_role": "tenant_admin",
            "tenant_id": uuid4(),
            "action": "content.created",
            "payload": {"title": "Test"},
            "created_at": datetime(2025, 1, 1, tzinfo=UTC),
        },
    )()


# list_audit_log


@pytest.mark.asyncio
async def test_list_audit_log_returns_formatted_entries(monkeypatch) -> None:
    actor_id = uuid4()
    entry = _fake_entry(actor_id)
    monkeypatch.setattr(
        "app.api.audit_log.tenant_service.get_audit_log_with_emails",
        AsyncMock(return_value=[(entry, "actor@example.com")]),
    )

    result = await list_audit_log(_manager(), AsyncMock(), limit=10)

    assert len(result) == 1
    assert result[0].actor_id == actor_id
    assert result[0].actor_email == "actor@example.com"
    assert result[0].action == "content.created"
    assert result[0].payload == {"title": "Test"}
    assert result[0].created_at == "2025-01-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_list_audit_log_handles_none_actor_email(monkeypatch) -> None:
    entry = _fake_entry()
    monkeypatch.setattr(
        "app.api.audit_log.tenant_service.get_audit_log_with_emails",
        AsyncMock(return_value=[(entry, None)]),
    )

    result = await list_audit_log(_manager(), AsyncMock(), limit=10)

    assert result[0].actor_email is None


@pytest.mark.asyncio
async def test_list_audit_log_returns_empty_list(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.audit_log.tenant_service.get_audit_log_with_emails",
        AsyncMock(return_value=[]),
    )

    result = await list_audit_log(_manager(), AsyncMock(), limit=10)

    assert result == []


@pytest.mark.asyncio
async def test_list_audit_log_returns_multiple_entries(monkeypatch) -> None:
    entries = [(_fake_entry(), f"user{i}@example.com") for i in range(3)]
    monkeypatch.setattr(
        "app.api.audit_log.tenant_service.get_audit_log_with_emails",
        AsyncMock(return_value=entries),
    )

    result = await list_audit_log(_manager(), AsyncMock(), limit=100)

    assert len(result) == 3
    assert result[1].actor_email == "user1@example.com"
