"""Widget config repository."""

import uuid

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WidgetConfig


async def delete_by_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Delete all widget configs for a tenant. Called by the erasure service."""
    result = await session.execute(
        delete(WidgetConfig).where(WidgetConfig.tenant_id == tenant_id)
    )
    return result.rowcount
