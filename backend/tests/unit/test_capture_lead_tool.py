from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.schemas import CaptureLeadInput, CaptureLeadOutput, ToolError
from app.tools.capture_lead import MAX_LEADS_PER_SESSION_PER_HOUR, capture_lead


@pytest.fixture
def fake_session() -> AsyncMock:
    return AsyncMock()


@pytest.mark.asyncio
async def test_creates_lead_when_under_limit(fake_session: AsyncMock) -> None:
    lead_id = uuid4()
    tenant_id = uuid4()

    async def fake_create(**kwargs) -> object:
        return type("FakeLead", (), {"id": lead_id})()

    fake_session.reset_mock()
    with (
        patch(
            "app.tools.capture_lead.lead_repo.create",
            side_effect=fake_create,
        ),
        patch(
            "app.tools.capture_lead.lead_repo.count_recent_by_session",
            AsyncMock(return_value=0),
        ),
    ):
        result = await capture_lead(
            tenant_id=tenant_id,
            tool_input=CaptureLeadInput(
                visitor_name="Jane",
                contact="jane@example.com",
                intent="Pricing inquiry",
                session_id="session-1",
            ),
            session=fake_session,
        )

    assert isinstance(result, CaptureLeadOutput)
    assert result.lead_id == lead_id
    assert result.status == "captured"


@pytest.mark.asyncio
async def test_returns_rate_limited_when_over_limit(
    fake_session: AsyncMock,
) -> None:
    with patch(
        "app.tools.capture_lead.lead_repo.count_recent_by_session",
        AsyncMock(return_value=MAX_LEADS_PER_SESSION_PER_HOUR),
    ):
        result = await capture_lead(
            tenant_id=uuid4(),
            tool_input=CaptureLeadInput(
                visitor_name="Jane",
                contact="jane@example.com",
                intent="Help",
                session_id="session-1",
            ),
            session=fake_session,
        )

    assert isinstance(result, ToolError)
    assert result.tool == "capture_lead"
    assert result.code == "rate_limited"


@pytest.mark.asyncio
async def test_returns_database_unavailable_when_session_is_none() -> None:
    result = await capture_lead(
        tenant_id=uuid4(),
        tool_input=CaptureLeadInput(
            contact="jane@example.com",
            intent="Help",
            session_id="session-1",
        ),
        session=None,
    )

    assert isinstance(result, ToolError)
    assert result.tool == "capture_lead"
    assert result.code == "database_unavailable"


def test_capture_lead_input_rejects_tenant_id() -> None:
    with pytest.raises(ValueError):
        CaptureLeadInput.model_validate(
            {
                "contact": "jane@example.com",
                "intent": "Help",
                "session_id": "session-1",
                "tenant_id": str(uuid4()),
            }
        )
