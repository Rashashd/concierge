"""Cost reporting endpoints — require tenant_manager role."""

import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_session, require_tenant_manager
from app.repositories import cost_records as cost_repo
from app.schemas import TenantCostResponse, UserContext

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("/{tenant_id}/cost", response_model=TenantCostResponse)
async def get_tenant_cost(
    tenant_id: uuid.UUID,
    _: Annotated[UserContext, Depends(require_tenant_manager)],
    session: Annotated[AsyncSession, Depends(get_session)],
    start_day: Annotated[
        date | None,
        Query(description="Start of date range (UTC, YYYY-MM-DD). Defaults to today."),
    ] = None,
    end_day: Annotated[
        date | None,
        Query(description="End of inclusive date range (UTC). Defaults to start_day."),
    ] = None,
) -> TenantCostResponse:
    today = datetime.now(UTC).date()
    if start_day is None:
        start_day = today
    if end_day is None:
        end_day = start_day
    if end_day < start_day:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_day must be on or after start_day",
        )
    totals = await cost_repo.get_range_totals(session, tenant_id, start_day, end_day)
    return TenantCostResponse(
        tenant_id=tenant_id, start_day=start_day, end_day=end_day, **totals
    )
