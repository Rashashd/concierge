"""Tenant business logic — multi-step operations spanning several repositories."""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog
from app.infra.minio import MinioClient
from app.repositories import audit_log as audit_repo
from app.repositories import tenants as tenant_repo
from app.repositories import users as user_repo
from app.services.erasure import erase_tenant
from app.services.memory import RedisMemoryClient

logger = structlog.get_logger(__name__)


async def get_audit_log_with_emails(
    session: AsyncSession,
    limit: int = 100,
) -> list[tuple[AuditLog, str | None]]:
    """Return audit log entries paired with each actor's email address."""
    entries = await audit_repo.list_all(session, limit=limit)
    actor_ids = {e.actor_id for e in entries}
    email_map = await user_repo.get_emails_by_ids(session, actor_ids)
    return [(e, email_map.get(e.actor_id)) for e in entries]


async def full_delete_tenant(
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: str,
    session: AsyncSession,
    redis: RedisMemoryClient,
    minio: MinioClient,
) -> None:
    """Erase all tenant data then delete the users and the tenant record itself."""
    await erase_tenant(
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_role=actor_role,
        session=session,
        redis=redis,
        minio=minio,
    )
    async with session.begin():
        await user_repo.delete_by_tenant(session, tenant_id)
        await tenant_repo.delete(session, tenant_id)
    logger.info("tenant.deleted", tenant_id=str(tenant_id))
