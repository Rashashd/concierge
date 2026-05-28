from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_admin_tenant_session,
    require_tenant_admin,
)
from app.repositories import leads as lead_repo
from app.schemas import LeadResponse, LeadStatusUpdate, UserContext

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=list[LeadResponse])
async def list_leads(
    user: Annotated[UserContext, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_admin_tenant_session)],
) -> list[LeadResponse]:
    leads = await lead_repo.list_by_tenant(
        session=session,
        tenant_id=user.tenant_id,  # type: ignore[arg-type]
    )
    return [
        LeadResponse(
            id=lead.id,
            tenant_id=lead.tenant_id,
            session_id=lead.session_id,
            visitor_name=lead.visitor_name,
            contact=lead.contact,
            intent=lead.intent,
            status=lead.status,
            created_at=lead.created_at.isoformat(),
        )
        for lead in leads
    ]


@router.patch("/{lead_id}", response_model=LeadResponse)
async def update_lead_status(
    lead_id: UUID,
    body: LeadStatusUpdate,
    user: Annotated[UserContext, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_admin_tenant_session)],
) -> LeadResponse:
    lead = await lead_repo.update_status(
        session=session,
        tenant_id=user.tenant_id,  # type: ignore[arg-type]
        lead_id=lead_id,
        status=body.status,
    )
    if lead is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lead not found",
        )
    return LeadResponse(
        id=lead.id,
        tenant_id=lead.tenant_id,
        session_id=lead.session_id,
        visitor_name=lead.visitor_name,
        contact=lead.contact,
        intent=lead.intent,
        status=lead.status,
        created_at=lead.created_at.isoformat(),
    )
