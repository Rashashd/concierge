from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_admin_tenant_session, require_tenant_admin
from app.repositories import audit_log as audit_repo
from app.schemas import EscalationResponse, UserContext

router = APIRouter(prefix="/escalations", tags=["escalations"])


@router.get("", response_model=list[EscalationResponse])
async def list_escalations(
    user: Annotated[UserContext, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_admin_tenant_session)],
) -> list[EscalationResponse]:
    # get_admin_tenant_session already rejects None tenant_id with 403;
    # the assert here narrows the type for mypy.
    assert user.tenant_id is not None
    logs = await audit_repo.list_escalations_by_tenant(
        session=session,
        tenant_id=user.tenant_id,
    )
    return [
        EscalationResponse(
            id=log.id,
            tenant_id=log.tenant_id,
            conversation_id=log.payload.get("conversation_id", ""),
            reason=log.payload.get("reason", ""),
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]
