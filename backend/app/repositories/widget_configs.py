"""Widget config repository."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WidgetConfig


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    widget_id: uuid.UUID | None = None,
) -> WidgetConfig:
    config = WidgetConfig(
        tenant_id=tenant_id,
        **({"widget_id": widget_id} if widget_id is not None else {}),
    )
    session.add(config)
    await session.flush()
    await session.refresh(config)
    return config


async def get_by_widget_id(
    session: AsyncSession,
    widget_id: uuid.UUID,
) -> WidgetConfig | None:
    result = await session.execute(
        select(WidgetConfig).where(WidgetConfig.widget_id == widget_id)
    )
    return result.scalar_one_or_none()


async def list_by_tenant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[WidgetConfig]:
    result = await session.execute(
        select(WidgetConfig)
        .where(WidgetConfig.tenant_id == tenant_id)
        .order_by(WidgetConfig.created_at)
    )
    return list(result.scalars().all())


async def delete_by_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Delete all widget configs for a tenant. Called by the erasure service."""
    result = await session.execute(
        delete(WidgetConfig).where(WidgetConfig.tenant_id == tenant_id)
    )
    return result.rowcount  # type: ignore[attr-defined, no-any-return]
