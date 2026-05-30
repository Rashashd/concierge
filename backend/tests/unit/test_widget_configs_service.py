"""Unit tests for the widget_configs service."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.widget_configs import resolve_widget_tenant, upsert_widget_config


def _mock_session() -> MagicMock:
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=None)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.begin.return_value = ctx
    return session


def _fake_config(tenant_id=None) -> MagicMock:
    config = MagicMock()
    config.widget_id = uuid4()
    config.tenant_id = tenant_id or uuid4()
    config.greeting = "Hello"
    config.theme_color = "#000000"
    config.enabled_tools = ["rag_search"]
    return config


# upsert_widget_config


@pytest.mark.asyncio
async def test_upsert_creates_config_when_none_exists(monkeypatch) -> None:
    tenant_id = uuid4()
    new_config = _fake_config(tenant_id)
    monkeypatch.setattr(
        "app.services.widget_configs.widget_config_repo.get_first_by_tenant",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.services.widget_configs.widget_config_repo.create",
        AsyncMock(return_value=new_config),
    )

    result = await upsert_widget_config(
        _mock_session(),
        tenant_id=tenant_id,
        greeting="Hi there",
        theme_color="#FF0000",
        enabled_tools=["rag_search"],
    )

    assert result is new_config
    assert result.greeting == "Hi there"
    assert result.theme_color == "#FF0000"


@pytest.mark.asyncio
async def test_upsert_updates_config_when_exists(monkeypatch) -> None:
    tenant_id = uuid4()
    existing = _fake_config(tenant_id)
    updated = _fake_config(tenant_id)
    updated.greeting = "New greeting"
    monkeypatch.setattr(
        "app.services.widget_configs.widget_config_repo.get_first_by_tenant",
        AsyncMock(return_value=existing),
    )
    update_mock = AsyncMock(return_value=updated)
    monkeypatch.setattr(
        "app.services.widget_configs.widget_config_repo.update_fields", update_mock
    )

    result = await upsert_widget_config(
        _mock_session(),
        tenant_id=tenant_id,
        greeting="New greeting",
        theme_color="#0000FF",
        enabled_tools=["rag_search", "escalate"],
    )

    update_mock.assert_awaited_once()
    assert result.greeting == "New greeting"


@pytest.mark.asyncio
async def test_upsert_does_not_call_create_when_updating(monkeypatch) -> None:
    existing = _fake_config()
    create_mock = AsyncMock()
    monkeypatch.setattr(
        "app.services.widget_configs.widget_config_repo.get_first_by_tenant",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(
        "app.services.widget_configs.widget_config_repo.update_fields",
        AsyncMock(return_value=existing),
    )
    monkeypatch.setattr(
        "app.services.widget_configs.widget_config_repo.create", create_mock
    )

    await upsert_widget_config(
        _mock_session(),
        tenant_id=uuid4(),
        greeting="G",
        theme_color="#000",
        enabled_tools=[],
    )

    create_mock.assert_not_called()


# resolve_widget_tenant


@pytest.mark.asyncio
async def test_resolve_returns_tenant_id_from_config(monkeypatch) -> None:
    widget_id = uuid4()
    tenant_id = uuid4()
    config = _fake_config(tenant_id)
    monkeypatch.setattr(
        "app.services.widget_configs.widget_config_repo.get_by_widget_id",
        AsyncMock(return_value=config),
    )

    result = await resolve_widget_tenant(MagicMock(), widget_id)

    assert result == tenant_id


@pytest.mark.asyncio
async def test_resolve_falls_back_to_widget_id_when_no_config(monkeypatch) -> None:
    widget_id = uuid4()
    monkeypatch.setattr(
        "app.services.widget_configs.widget_config_repo.get_by_widget_id",
        AsyncMock(return_value=None),
    )

    result = await resolve_widget_tenant(MagicMock(), widget_id)

    assert result == widget_id
