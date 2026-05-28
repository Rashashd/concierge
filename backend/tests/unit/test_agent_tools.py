import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from app.schemas import TenantContext, ToolError
from app.services.agent.nodes import RAG_SEARCH_TOOL, TOOLS, tool_node
from app.services.agent.state import AgentState


def test_tools_includes_rag_search_capture_lead_escalate() -> None:
    names = {tool.name for tool in TOOLS}
    assert names == {"rag_search", "capture_lead", "escalate"}


@pytest.mark.asyncio
async def test_tool_node_dispatches_capture_lead() -> None:
    tenant_id = uuid4()
    lead_id = uuid4()

    async def fake_capture_lead(**kwargs) -> object:
        result = type("FakeOutput", (), {})()
        result.lead_id = lead_id
        result.status = "captured"
        result.model_dump = lambda mode="json": {  # type: ignore[method-assign]
            "lead_id": str(lead_id),
            "status": "captured",
        }
        return result

    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "capture_lead",
                        "args": {
                            "visitor_name": "Jane",
                            "contact": "jane@example.com",
                            "intent": "Interest",
                            "session_id": "session-1",
                        },
                        "id": "call_1",
                    }
                ],
            )
        ],
        "tenant_context": TenantContext(
            tenant_id=tenant_id,
            widget_id=uuid4(),
            session_id="session-1",
        ),
        "conversation_id": "conv-1",
        "session": AsyncMock(),
    }

    with patch(
        "app.services.agent.nodes.capture_lead",
        side_effect=fake_capture_lead,
    ):
        result = await tool_node(state)

    messages = result["messages"]
    assert len(messages) == 2
    tool_msg = messages[-1]
    assert isinstance(tool_msg, ToolMessage)
    assert tool_msg.name == "capture_lead"
    payload = json.loads(tool_msg.content)
    assert payload["lead_id"] == str(lead_id)
    assert payload["status"] == "captured"


@pytest.mark.asyncio
async def test_tool_node_dispatches_escalate() -> None:
    tenant_id = uuid4()
    ticket_id = uuid4()

    async def fake_escalate(**kwargs) -> object:
        result = type("FakeOutput", (), {})()
        result.ticket_id = ticket_id
        result.status = "escalated"
        result.visitor_message = "Escalated."
        result.model_dump = lambda mode="json": {  # type: ignore[method-assign]
            "ticket_id": str(ticket_id),
            "status": "escalated",
            "visitor_message": "Escalated.",
        }
        return result

    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "escalate",
                        "args": {
                            "reason": "Need human",
                            "conversation_id": "conv-1",
                        },
                        "id": "call_2",
                    }
                ],
            )
        ],
        "tenant_context": TenantContext(
            tenant_id=tenant_id,
            widget_id=uuid4(),
            session_id="session-1",
        ),
        "conversation_id": "conv-1",
        "session": AsyncMock(),
    }

    with patch(
        "app.services.agent.nodes.escalate",
        side_effect=fake_escalate,
    ):
        result = await tool_node(state)

    messages = result["messages"]
    assert len(messages) == 2
    tool_msg = messages[-1]
    assert isinstance(tool_msg, ToolMessage)
    assert tool_msg.name == "escalate"
    payload = json.loads(tool_msg.content)
    assert payload["ticket_id"] == str(ticket_id)
    assert payload["status"] == "escalated"


@pytest.mark.asyncio
async def test_tool_node_unknown_tool_returns_error() -> None:
    state: AgentState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "nonexistent_tool",
                        "args": {},
                        "id": "call_3",
                    }
                ],
            )
        ],
        "tenant_context": TenantContext(
            tenant_id=uuid4(),
            widget_id=uuid4(),
            session_id="session-1",
        ),
        "conversation_id": "conv-1",
    }

    result = await tool_node(state)

    messages = result["messages"]
    tool_msg = messages[-1]
    assert isinstance(tool_msg, ToolMessage)
    error = ToolError.model_validate_json(tool_msg.content)
    assert error.tool == "nonexistent_tool"
    assert error.code == "unknown_tool"


@pytest.mark.asyncio
async def test_llm_visible_schemas_do_not_expose_tenant_id() -> None:
    assert "tenant_id" not in RAG_SEARCH_TOOL.args_schema.model_fields
    for tool in TOOLS:
        assert "tenant_id" not in tool.args_schema.model_fields
