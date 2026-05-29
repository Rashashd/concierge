"""Integration tests for the tenant repository — ORM construction and SQL scoping."""

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tenant
from app.repositories import tenants as tenant_repo


class FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def scalar_one_or_none(self) -> object:
        return self._rows[0] if self._rows else None

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list:
        return self._rows


class FakeSession:
    def __init__(self, rows: list | None = None) -> None:
        self.added: list = []
        self._rows = rows or []
        self.last_stmt: object = None

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass

    async def execute(self, stmt: object) -> FakeResult:
        self.last_stmt = stmt
        return FakeResult(self._rows)


@pytest.mark.asyncio
async def test_create_sets_name_and_slug() -> None:
    session = FakeSession()
    tenant = await tenant_repo.create(
        cast(AsyncSession, session),
        name="Acme Corp",
        slug="acme",
    )

    assert tenant.name == "Acme Corp"
    assert tenant.slug == "acme"
    assert len(session.added) == 1
    assert session.added[0] is tenant


@pytest.mark.asyncio
async def test_get_by_id_queries_by_tenant_id() -> None:
    tenant_id = uuid4()
    fake_tenant = Tenant(name="X", slug="x")
    session = FakeSession(rows=[fake_tenant])

    result = await tenant_repo.get_by_id(cast(AsyncSession, session), tenant_id)

    assert result is fake_tenant
    where_str = str(session.last_stmt.whereclause)
    assert "tenants.id" in where_str


@pytest.mark.asyncio
async def test_get_by_slug_queries_by_slug() -> None:
    fake_tenant = Tenant(name="Y", slug="y-corp")
    session = FakeSession(rows=[fake_tenant])

    result = await tenant_repo.get_by_slug(cast(AsyncSession, session), "y-corp")

    assert result is fake_tenant
    where_str = str(session.last_stmt.whereclause)
    assert "slug" in where_str


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_not_found() -> None:
    session = FakeSession(rows=[])
    result = await tenant_repo.get_by_id(cast(AsyncSession, session), uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_list_all_returns_all_tenants() -> None:
    tenants = [Tenant(name="A", slug="a"), Tenant(name="B", slug="b")]
    session = FakeSession(rows=tenants)

    result = await tenant_repo.list_all(cast(AsyncSession, session))

    assert result == tenants


@pytest.mark.asyncio
async def test_suspend_sets_is_active_false_and_records_timestamp() -> None:
    tenant_id = uuid4()
    fake_tenant = Tenant(name="Z", slug="z")
    fake_tenant.is_active = True
    session = FakeSession(rows=[fake_tenant])

    before = datetime.now(UTC)
    result = await tenant_repo.suspend(cast(AsyncSession, session), tenant_id)
    after = datetime.now(UTC)

    assert result is fake_tenant
    assert result.is_active is False
    assert result.suspended_at is not None
    assert before <= result.suspended_at.replace(tzinfo=UTC) <= after


@pytest.mark.asyncio
async def test_suspend_returns_none_when_tenant_not_found() -> None:
    session = FakeSession(rows=[])
    result = await tenant_repo.suspend(cast(AsyncSession, session), uuid4())
    assert result is None
