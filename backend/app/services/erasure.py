"""Right-to-erasure orchestration for tenant data."""

import uuid

import structlog
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.minio import MinioClient
from app.repositories import audit_log as audit_repo
from app.repositories import chunks as chunk_repo
from app.repositories import content as content_repo
from app.repositories import leads as lead_repo
from app.repositories import widget_configs as widget_config_repo
from app.services.memory import RedisMemoryClient, delete_tenant_sessions

logger = structlog.get_logger(__name__)


class ErasureReport(BaseModel):
    tenant_id: uuid.UUID
    chunks_deleted: int
    content_items_deleted: int
    leads_deleted: int
    widget_configs_deleted: int
    redis_sessions_deleted: int
    minio_objects_deleted: int


async def erase_tenant(
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: str,
    session: AsyncSession,
    redis: RedisMemoryClient,
    minio: MinioClient,
) -> ErasureReport:
    log = logger.bind(tenant_id=str(tenant_id), actor_id=str(actor_id))
    log.info("erasure.started")

    # Step 1: Postgres — atomic
    async with session.begin():
        # Satisfy RLS on tenant-scoped tables for the target tenant.
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"),
            {"tid": str(tenant_id)},
        )
        # FK-safe order: chunks reference content_items.
        chunks_deleted = await chunk_repo.delete_by_tenant(session, tenant_id)
        content_items_deleted = await content_repo.delete_by_tenant(session, tenant_id)
        leads_deleted = await lead_repo.delete_by_tenant(session, tenant_id)
        widget_configs_deleted = await widget_config_repo.delete_by_tenant(
            session, tenant_id
        )
        await audit_repo.create(
            session,
            actor_id=actor_id,
            actor_role=actor_role,
            tenant_id=tenant_id,
            action="tenant.erased",
            payload={
                "chunks_deleted": chunks_deleted,
                "content_items_deleted": content_items_deleted,
                "leads_deleted": leads_deleted,
                "widget_configs_deleted": widget_configs_deleted,
            },
        )

    log.info(
        "erasure.postgres_complete",
        chunks=chunks_deleted,
        content_items=content_items_deleted,
        leads=leads_deleted,
        widget_configs=widget_configs_deleted,
    )

    # Step 2: Redis — best-effort
    redis_sessions_deleted = 0
    try:
        redis_sessions_deleted = await delete_tenant_sessions(redis, tenant_id)
        log.info("erasure.redis_complete", sessions=redis_sessions_deleted)
    except Exception as exc:
        log.exception("erasure.redis_failed", error_type=type(exc).__name__)

    # Step 3: MinIO — best-effort
    minio_objects_deleted = 0
    try:
        minio_objects_deleted = await minio.delete_tenant_prefix(tenant_id)
        log.info("erasure.minio_complete", objects=minio_objects_deleted)
    except Exception as exc:
        log.exception("erasure.minio_failed", error_type=type(exc).__name__)

    log.info("erasure.complete")
    return ErasureReport(
        tenant_id=tenant_id,
        chunks_deleted=chunks_deleted,
        content_items_deleted=content_items_deleted,
        leads_deleted=leads_deleted,
        widget_configs_deleted=widget_configs_deleted,
        redis_sessions_deleted=redis_sessions_deleted,
        minio_objects_deleted=minio_objects_deleted,
    )
