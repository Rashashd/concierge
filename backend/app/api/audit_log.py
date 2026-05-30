"""Audit log endpoints — require tenant_manager role."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_session, require_tenant_manager
from app.schemas import AuditLogResponse, UserContext
from app.services import tenants as tenant_service

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("/audit", response_model=list[AuditLogResponse])
async def list_audit_log(
    _: Annotated[UserContext, Depends(require_tenant_manager)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditLogResponse]:
    entries = await tenant_service.get_audit_log_with_emails(session, limit=limit)
    return [
        AuditLogResponse(
            id=e.id,
            actor_id=e.actor_id,
            actor_email=email,
            actor_role=e.actor_role,
            tenant_id=e.tenant_id,
            action=e.action,
            payload=e.payload,
            created_at=e.created_at.isoformat(),
        )
        for e, email in entries
    ]
