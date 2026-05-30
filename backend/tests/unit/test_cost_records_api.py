"""Unit tests for the /tenants/{tenant_id}/cost endpoint."""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.cost_records import get_tenant_cost
from app.schemas import UserContext


def _manager() -> UserContext:
    return UserContext(user_id=uuid4(), role="tenant_manager", tenant_id=None)


def _zero_totals() -> dict:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


# get_tenant_cost


@pytest.mark.asyncio
async def test_get_tenant_cost_returns_totals_for_date_range(monkeypatch) -> None:
    tenant_id = uuid4()
    start = date(2025, 1, 1)
    end = date(2025, 1, 31)
    monkeypatch.setattr(
        "app.api.cost_records.cost_repo.get_range_totals",
        AsyncMock(
            return_value={
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            }
        ),
    )

    result = await get_tenant_cost(
        tenant_id, _manager(), AsyncMock(), start_day=start, end_day=end
    )

    assert result.tenant_id == tenant_id
    assert result.start_day == start
    assert result.end_day == end
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 50
    assert result.total_tokens == 150


@pytest.mark.asyncio
async def test_get_tenant_cost_raises_400_when_end_before_start() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_tenant_cost(
            uuid4(),
            _manager(),
            AsyncMock(),
            start_day=date(2025, 1, 31),
            end_day=date(2025, 1, 1),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_get_tenant_cost_defaults_to_today_when_no_dates(monkeypatch) -> None:
    today = datetime.now(UTC).date()
    monkeypatch.setattr(
        "app.api.cost_records.cost_repo.get_range_totals",
        AsyncMock(return_value=_zero_totals()),
    )

    result = await get_tenant_cost(
        uuid4(), _manager(), AsyncMock(), start_day=None, end_day=None
    )

    assert result.start_day == today
    assert result.end_day == today


@pytest.mark.asyncio
async def test_get_tenant_cost_defaults_end_day_to_start_day(monkeypatch) -> None:
    start = date(2025, 6, 15)
    monkeypatch.setattr(
        "app.api.cost_records.cost_repo.get_range_totals",
        AsyncMock(return_value=_zero_totals()),
    )

    result = await get_tenant_cost(
        uuid4(), _manager(), AsyncMock(), start_day=start, end_day=None
    )

    assert result.end_day == start


@pytest.mark.asyncio
async def test_get_tenant_cost_accepts_same_day_range(monkeypatch) -> None:
    same_day = date(2025, 3, 1)
    monkeypatch.setattr(
        "app.api.cost_records.cost_repo.get_range_totals",
        AsyncMock(return_value=_zero_totals()),
    )

    result = await get_tenant_cost(
        uuid4(), _manager(), AsyncMock(), start_day=same_day, end_day=same_day
    )

    assert result.start_day == result.end_day == same_day
