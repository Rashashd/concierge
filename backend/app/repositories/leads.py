"""Lead repository — create and manage captured leads."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lead


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    session_id: str,
    contact: str,
    intent: str,
    visitor_name: str | None = None,
) -> Lead:
    lead = Lead(
        tenant_id=tenant_id,
        session_id=session_id,
        contact=contact,
        intent=intent,
        visitor_name=visitor_name,
    )
    session.add(lead)
    await session.flush()
    await session.refresh(lead)
    return lead


async def get_by_id(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    lead_id: uuid.UUID,
) -> Lead | None:
    result = await session.execute(
        select(Lead).where(
            Lead.id == lead_id,
            Lead.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def list_by_tenant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[Lead]:
    result = await session.execute(
        select(Lead).where(Lead.tenant_id == tenant_id).order_by(Lead.created_at.desc())
    )
    return list(result.scalars().all())


async def update_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    lead_id: uuid.UUID,
    status: str,
) -> Lead | None:
    lead = await get_by_id(session, tenant_id, lead_id)
    if lead is None:
        return None
    lead.status = status
    await session.flush()
    return lead


async def count_recent_by_session(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    session_id: str,
    window_seconds: int = 3600,
) -> int:
    """Count lead writes for a session_id within the rolling window.

    Used for rate limiting.
    """
    since = datetime.now(UTC) - timedelta(seconds=window_seconds)
    result = await session.execute(
        select(func.count()).where(
            Lead.tenant_id == tenant_id,
            Lead.session_id == session_id,
            Lead.created_at >= since,
        )
    )
    return int(result.scalar_one())


async def delete_by_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Delete all leads for a tenant. Called by the erasure service."""
    result = await session.execute(delete(Lead).where(Lead.tenant_id == tenant_id))
    return result.rowcount
