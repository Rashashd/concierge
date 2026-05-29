"""Audit log repository — insert-only. No RLS; access enforced at the route layer."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


async def list_escalations_by_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    limit: int = 100,
) -> list[AuditLog]:
    """Return audit log rows for escalated conversations belonging to tenant_id.

    Isolation is enforced here rather than via RLS because audit_logs has no
    RLS policy (it is insert-only and cross-tenant for platform-level queries).
    """
    result = await session.execute(
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(AuditLog.action == "conversation.escalated")
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def create(
    session: AsyncSession,
    *,
    actor_id: uuid.UUID,
    actor_role: str,
    action: str,
    tenant_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    log = AuditLog(
        actor_id=actor_id,
        actor_role=actor_role,
        tenant_id=tenant_id,
        action=action,
        payload=payload or {},
    )
    session.add(log)
    await session.flush()
    return log
