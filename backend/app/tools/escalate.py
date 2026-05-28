from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import audit_log as audit_log_repo
from app.schemas import EscalateInput, EscalateOutput, ToolError

TOOL_NAME = "escalate"

VISITOR_MESSAGE = "I've escalated this conversation to a human team member."


async def escalate(
    tenant_id: UUID,
    tool_input: EscalateInput,
    session: AsyncSession | None,
) -> EscalateOutput | ToolError:
    if session is None:
        return ToolError(
            tool=TOOL_NAME,
            code="database_unavailable",
            message="Database session is not available.",
        )

    try:
        log = await audit_log_repo.create(
            session=session,
            actor_id=tenant_id,
            actor_role="system",
            action="conversation.escalated",
            tenant_id=tenant_id,
            payload={
                "conversation_id": tool_input.conversation_id,
                "reason": tool_input.reason,
            },
        )
    except Exception as exc:
        return ToolError(
            tool=TOOL_NAME,
            code="database_error",
            message=f"Failed to write escalation audit log: {exc}",
        )

    return EscalateOutput(
        ticket_id=log.id,
        status="escalated",
        visitor_message=VISITOR_MESSAGE,
    )
