"""Audit log repository — insert-only. No RLS; access enforced at the route layer."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog


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
