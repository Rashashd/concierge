"""Integration tests for the cost records repository — insert and daily aggregate."""

from datetime import date
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import cost_records as cost_repo


class FakeResult:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def one(self) -> object:
        return self._rows[0]


class FakeSession:
    def __init__(self, rows: list | None = None) -> None:
        self.added: list = []
        self._rows = rows or []
        self.last_stmt: object = None

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        pass

    async def execute(self, stmt: object) -> FakeResult:
        self.last_stmt = stmt
        return FakeResult(self._rows)


@pytest.mark.asyncio
async def test_create_sets_all_token_fields() -> None:
    tenant_id = uuid4()
    session = FakeSession()

    record = await cost_repo.create(
        cast(AsyncSession, session),
        tenant_id=tenant_id,
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
    )

    assert record.tenant_id == tenant_id
    assert record.model == "gpt-4o-mini"
    assert record.prompt_tokens == 100
    assert record.completion_tokens == 50
    assert record.total_tokens == 150
    assert len(session.added) == 1


@pytest.mark.asyncio
async def test_get_daily_totals_returns_summed_values() -> None:
    fake_row = SimpleNamespace(
        prompt_tokens=200,
        completion_tokens=80,
        total_tokens=280,
    )
    session = FakeSession(rows=[fake_row])

    result = await cost_repo.get_daily_totals(
        cast(AsyncSession, session),
        tenant_id=uuid4(),
        day=date(2026, 5, 29),
    )

    assert result == {
        "prompt_tokens": 200,
        "completion_tokens": 80,
        "total_tokens": 280,
    }


@pytest.mark.asyncio
async def test_get_daily_totals_query_filters_by_tenant_id_and_date_range() -> None:
    fake_row = SimpleNamespace(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    session = FakeSession(rows=[fake_row])

    await cost_repo.get_daily_totals(
        cast(AsyncSession, session),
        tenant_id=uuid4(),
        day=date(2026, 5, 29),
    )

    where_str = str(session.last_stmt.whereclause)
    assert "tenant_id" in where_str
    assert "recorded_at" in where_str
