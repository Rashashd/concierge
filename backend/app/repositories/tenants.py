"""Tenant repository — CRUD operations for tenant provisioning."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tenant


async def create(session: AsyncSession, *, name: str, slug: str) -> Tenant:
    tenant = Tenant(name=name, slug=slug)
    session.add(tenant)
    await session.flush()
    await session.refresh(tenant)
    return tenant


async def list_all(session: AsyncSession) -> list[Tenant]:
    result = await session.execute(select(Tenant).order_by(Tenant.created_at))
    return list(result.scalars().all())


async def get_by_id(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
    return result.scalar_one_or_none()


async def get_by_slug(session: AsyncSession, slug: str) -> Tenant | None:
    result = await session.execute(select(Tenant).where(Tenant.slug == slug))
    return result.scalar_one_or_none()


async def suspend(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    tenant = await get_by_id(session, tenant_id)
    if tenant is None:
        return None
    tenant.is_active = False
    tenant.suspended_at = datetime.now(UTC)
    await session.flush()
    return tenant
