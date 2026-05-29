"""Smoke tests for the leads management pipeline.

Calls the real route handlers + real repo functions against a fake session.
Verifies tenant scoping and status update flow without a live database.
"""

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.leads import list_leads, update_lead_status
from app.db.models import Lead
from app.schemas import LeadStatusUpdate, UserContext

# ── Shared fakes ──────────────────────────────────────────────────────────────


class FakeResult:
    def __init__(self, rows: list | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> object:
        return self._rows[0] if self._rows else None

    def scalars(self) -> "FakeResult":
        return self

    def all(self) -> list:
        return self._rows


class FakeSession:
    def __init__(self, results: list[FakeResult] | None = None) -> None:
        self.added: list = []
        self._results: list[FakeResult] = list(results or [])

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def refresh(self, obj: object) -> None:
        pass

    async def execute(
        self, stmt: object, *args: object, **kwargs: object
    ) -> FakeResult:
        if self._results:
            return self._results.pop(0)
        return FakeResult()


def _admin() -> UserContext:
    return UserContext(user_id=uuid4(), role="tenant_admin", tenant_id=uuid4())


def _lead(tenant_id: object, status: str = "new") -> Lead:
    lead = Lead(
        tenant_id=tenant_id,  # type: ignore[arg-type]
        session_id="sess-abc",
        contact="alice@example.com",
        intent="pricing inquiry",
        visitor_name="Alice",
    )
    lead.id = uuid4()  # type: ignore[assignment]
    lead.status = status
    lead.created_at = datetime.now(UTC)
    return lead


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_smoke_list_leads_returns_tenant_leads() -> None:
    user = _admin()
    leads = [_lead(user.tenant_id), _lead(user.tenant_id)]
    session = FakeSession(results=[FakeResult(rows=leads)])

    result = await list_leads(user, cast(AsyncSession, session))

    assert len(result) == 2
    assert all(r.contact == "alice@example.com" for r in result)
    assert all(r.tenant_id == user.tenant_id for r in result)


@pytest.mark.asyncio
async def test_smoke_list_leads_returns_empty_when_none() -> None:
    user = _admin()
    session = FakeSession(results=[FakeResult(rows=[])])

    result = await list_leads(user, cast(AsyncSession, session))

    assert result == []


@pytest.mark.asyncio
async def test_smoke_update_lead_status_transitions_to_contacted() -> None:
    user = _admin()
    lead = _lead(user.tenant_id, status="new")
    # get_by_id calls execute once
    session = FakeSession(results=[FakeResult(rows=[lead])])

    result = await update_lead_status(
        lead.id,  # type: ignore[arg-type]
        LeadStatusUpdate(status="contacted"),
        user,
        cast(AsyncSession, session),
    )

    assert result.status == "contacted"
    assert result.contact == "alice@example.com"


@pytest.mark.asyncio
async def test_smoke_update_lead_status_raises_404_when_not_found() -> None:
    user = _admin()
    session = FakeSession(results=[FakeResult(rows=[])])

    with pytest.raises(HTTPException) as exc_info:
        await update_lead_status(
            uuid4(),
            LeadStatusUpdate(status="contacted"),
            user,
            cast(AsyncSession, session),
        )

    assert exc_info.value.status_code == 404
