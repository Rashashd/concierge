from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.schemas import EscalateInput, EscalateOutput, ToolError
from app.tools.escalate import VISITOR_MESSAGE, escalate


@pytest.fixture
def fake_session() -> AsyncMock:
    return AsyncMock()


@pytest.mark.asyncio
async def test_writes_audit_log_with_escalate_action(
    fake_session: AsyncMock,
) -> None:
    tenant_id = uuid4()
    log_id = uuid4()

    async def fake_create(**kwargs) -> object:
        return type("FakeAuditLog", (), {"id": log_id})()

    fake_session.reset_mock()
    with patch(
        "app.tools.escalate.audit_log_repo.create",
        side_effect=fake_create,
    ) as mock_create:
        result = await escalate(
            tenant_id=tenant_id,
            tool_input=EscalateInput(
                reason="Visitor requested human",
                conversation_id="conv-1",
            ),
            session=fake_session,
        )

    mock_create.assert_awaited_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["action"] == "conversation.escalated"
    assert kwargs["tenant_id"] == tenant_id
    assert kwargs["actor_id"] == tenant_id
    assert kwargs["actor_role"] == "system"
    assert kwargs["payload"]["reason"] == "Visitor requested human"
    assert kwargs["payload"]["conversation_id"] == "conv-1"

    assert isinstance(result, EscalateOutput)
    assert result.ticket_id == log_id
    assert result.status == "escalated"
    assert result.visitor_message == VISITOR_MESSAGE


@pytest.mark.asyncio
async def test_returns_database_unavailable_when_session_is_none() -> None:
    result = await escalate(
        tenant_id=uuid4(),
        tool_input=EscalateInput(
            reason="Need help",
            conversation_id="conv-1",
        ),
        session=None,
    )

    assert isinstance(result, ToolError)
    assert result.tool == "escalate"
    assert result.code == "database_unavailable"


def test_escalate_input_rejects_tenant_id() -> None:
    with pytest.raises(ValueError):
        EscalateInput.model_validate(
            {
                "reason": "Need help",
                "conversation_id": "conv-1",
                "tenant_id": str(uuid4()),
            }
        )
