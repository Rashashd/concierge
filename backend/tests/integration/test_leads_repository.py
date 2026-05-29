"""Integration tests for the leads repository — tenant scoping and rate-limit query."""

from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lead
from app.repositories import leads as leads_repo


class FakeResult:
    def __init__(self, rows: list, rowcount: int = 1) -> None:
        self._rows = rows
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> object:
        return self._rows[0] if self._rows else None

    def scalar_one(self) -> object:
        return self._rows[0]

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
async def test_create_sets_all_fields() -> None:
    tenant_id = uuid4()
    session = FakeSession()

    lead = await leads_repo.create(
        cast(AsyncSession, session),
        tenant_id=tenant_id,
        session_id="sess-abc",
        contact="user@example.com",
        intent="pricing inquiry",
        visitor_name="Alice",
    )

    assert lead.tenant_id == tenant_id
    assert lead.session_id == "sess-abc"
    assert lead.contact == "user@example.com"
    assert lead.intent == "pricing inquiry"
    assert lead.visitor_name == "Alice"
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_get_by_id_scopes_by_tenant_id() -> None:
    tenant_id = uuid4()
    lead_id = uuid4()
    fake_lead = Lead(
        tenant_id=tenant_id,
        session_id="s",
        contact="c@c.com",
        intent="i",
    )
    session = FakeSession(rows=[fake_lead])

    result = await leads_repo.get_by_id(cast(AsyncSession, session), tenant_id, lead_id)

    assert result is fake_lead
    where_str = str(session.last_stmt.whereclause)
    assert "tenant_id" in where_str
    assert "leads.id" in where_str


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_not_found() -> None:
    session = FakeSession(rows=[])
    result = await leads_repo.get_by_id(cast(AsyncSession, session), uuid4(), uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_count_recent_by_session_filters_tenant_session_and_time() -> None:
    session = FakeSession(rows=[5])

    count = await leads_repo.count_recent_by_session(
        cast(AsyncSession, session),
        tenant_id=uuid4(),
        session_id="sess-abc",
        window_seconds=3600,
    )

    assert count == 5
    where_str = str(session.last_stmt.whereclause)
    assert "tenant_id" in where_str
    assert "session_id" in where_str
    assert "created_at" in where_str


@pytest.mark.asyncio
async def test_update_status_sets_status_field() -> None:
    tenant_id = uuid4()
    lead_id = uuid4()
    fake_lead = Lead(
        tenant_id=tenant_id,
        session_id="s",
        contact="c@c.com",
        intent="i",
    )
    fake_lead.status = "new"
    session = FakeSession(rows=[fake_lead])

    result = await leads_repo.update_status(
        cast(AsyncSession, session), tenant_id, lead_id, "contacted"
    )

    assert result is fake_lead
    assert result.status == "contacted"


@pytest.mark.asyncio
async def test_update_status_returns_none_when_lead_not_found() -> None:
    session = FakeSession(rows=[])
    result = await leads_repo.update_status(
        cast(AsyncSession, session), uuid4(), uuid4(), "contacted"
    )
    assert result is None
