"""Cost records repository — insert and aggregate token usage per tenant."""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CostRecord


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
) -> CostRecord:
    record = CostRecord(
        tenant_id=tenant_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
    session.add(record)
    await session.flush()
    return record


async def get_daily_totals(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    day: date,
) -> dict[str, int]:
    """Return summed token counts for a tenant on a given calendar day (UTC)."""
    day_start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    result = await session.execute(
        select(
            func.coalesce(func.sum(CostRecord.prompt_tokens), 0).label("prompt_tokens"),
            func.coalesce(func.sum(CostRecord.completion_tokens), 0).label(
                "completion_tokens"
            ),
            func.coalesce(func.sum(CostRecord.total_tokens), 0).label("total_tokens"),
        ).where(
            CostRecord.tenant_id == tenant_id,
            CostRecord.recorded_at >= day_start,
            CostRecord.recorded_at < day_end,
        )
    )
    row = result.one()
    return {
        "prompt_tokens": int(row.prompt_tokens),
        "completion_tokens": int(row.completion_tokens),
        "total_tokens": int(row.total_tokens),
    }
