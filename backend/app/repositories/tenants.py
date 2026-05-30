"""Tenant repository — CRUD operations for tenant provisioning."""

import uuid
from datetime import UTC, datetime
from typing import Any

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


async def unsuspend(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    tenant = await get_by_id(session, tenant_id)
    if tenant is None:
        return None
    tenant.is_active = True
    tenant.suspended_at = None
    await session.flush()
    return tenant


async def delete(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    tenant = await get_by_id(session, tenant_id)
    if tenant is None:
        return False
    await session.delete(tenant)
    return True


async def update_config(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    llm_persona: str | None,
    guardrail_config: dict[str, Any] | None,
) -> Tenant | None:
    tenant = await get_by_id(session, tenant_id)
    if tenant is None:
        return None
    if llm_persona is not None:
        tenant.llm_persona = llm_persona
    if guardrail_config is not None:
        tenant.guardrail_config = guardrail_config
    await session.flush()
    return tenant
