"""Integration tests for the widget configs repository."""

from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WidgetConfig
from app.repositories import widget_configs as widget_repo


class FakeResult:
    def __init__(self, rows: list, rowcount: int = 1) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> object:
        return self._rows[0] if self._rows else None

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list:
        return self._rows


class FakeSession:
    def __init__(self, rows: list | None = None, rowcount: int = 1) -> None:
        self.added: list = []
        self._rows = rows or []
        self._rowcount = rowcount
        self.last_stmt: object = None

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass

    async def execute(self, stmt: object) -> FakeResult:
        self.last_stmt = stmt
        return FakeResult(self._rows, self._rowcount)


@pytest.mark.asyncio
async def test_create_sets_tenant_id() -> None:
    tenant_id = uuid4()
    session = FakeSession()

    config = await widget_repo.create(
        cast(AsyncSession, session),
        tenant_id=tenant_id,
    )

    assert config.tenant_id == tenant_id
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_create_with_explicit_widget_id() -> None:
    tenant_id = uuid4()
    widget_id = uuid4()
    session = FakeSession()

    config = await widget_repo.create(
        cast(AsyncSession, session),
        tenant_id=tenant_id,
        widget_id=widget_id,
    )

    assert config.tenant_id == tenant_id
    assert config.widget_id == widget_id


@pytest.mark.asyncio
async def test_get_by_widget_id_queries_by_widget_id() -> None:
    widget_id = uuid4()
    fake_config = WidgetConfig(tenant_id=uuid4(), widget_id=widget_id)
    session = FakeSession(rows=[fake_config])

    result = await widget_repo.get_by_widget_id(cast(AsyncSession, session), widget_id)

    assert result is fake_config
    where_str = str(session.last_stmt.whereclause)
    assert "widget_id" in where_str


@pytest.mark.asyncio
async def test_get_by_widget_id_returns_none_when_not_found() -> None:
    session = FakeSession(rows=[])
    result = await widget_repo.get_by_widget_id(cast(AsyncSession, session), uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_list_by_tenant_filters_by_tenant_id() -> None:
    tenant_id = uuid4()
    configs = [
        WidgetConfig(tenant_id=tenant_id, widget_id=uuid4()),
        WidgetConfig(tenant_id=tenant_id, widget_id=uuid4()),
    ]
    session = FakeSession(rows=configs)

    result = await widget_repo.list_by_tenant(cast(AsyncSession, session), tenant_id)

    assert result == configs
    where_str = str(session.last_stmt.whereclause)
    assert "tenant_id" in where_str


@pytest.mark.asyncio
async def test_delete_by_tenant_scopes_delete_by_tenant_id() -> None:
    session = FakeSession(rows=[], rowcount=3)

    count = await widget_repo.delete_by_tenant(cast(AsyncSession, session), uuid4())

    assert count == 3
    where_str = str(session.last_stmt.whereclause)
    assert "tenant_id" in where_str
