from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import leads as lead_repo
from app.schemas import CaptureLeadInput, CaptureLeadOutput, ToolError

TOOL_NAME = "capture_lead"

MAX_LEADS_PER_SESSION_PER_HOUR = 3


async def capture_lead(
    tenant_id: UUID,
    tool_input: CaptureLeadInput,
    session: AsyncSession | None,
) -> CaptureLeadOutput | ToolError:
    if session is None:
        return ToolError(
            tool=TOOL_NAME,
            code="database_unavailable",
            message="Database session is not available.",
        )

    try:
        recent_count = await lead_repo.count_recent_by_session(
            session=session,
            tenant_id=tenant_id,
            session_id=tool_input.session_id,
        )
    except Exception as exc:
        return ToolError(
            tool=TOOL_NAME,
            code="database_error",
            message=f"Failed to check lead rate limit: {exc}",
        )

    if recent_count >= MAX_LEADS_PER_SESSION_PER_HOUR:
        return ToolError(
            tool=TOOL_NAME,
            code="rate_limited",
            message=(
                "Too many lead captures for this session. "
                "Please wait before trying again."
            ),
        )

    try:
        lead = await lead_repo.create(
            session=session,
            tenant_id=tenant_id,
            session_id=tool_input.session_id,
            contact=tool_input.contact,
            intent=tool_input.intent,
            visitor_name=tool_input.visitor_name,
        )
    except Exception as exc:
        return ToolError(
            tool=TOOL_NAME,
            code="database_error",
            message=f"Failed to create lead: {exc}",
        )

    return CaptureLeadOutput(lead_id=lead.id, status="captured")
