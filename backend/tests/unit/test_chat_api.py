from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.chat import chat
from app.schemas import ChatRequest, TenantContext


class FakeFinalModel:
    def bind_tools(self, tools: object) -> "FakeFinalModel":
        return self

    async def ainvoke(self, messages: object) -> object:
        from langchain_core.messages import AIMessage

        return AIMessage(content="Tenant-safe response.")


@pytest.mark.asyncio
async def test_chat_returns_agent_response_with_verified_tenant_context() -> None:
    tenant_context = TenantContext(
        tenant_id=uuid4(),
        widget_id=uuid4(),
        session_id="session-1",
    )
    response = await chat(
        request=ChatRequest(message="Hello", conversation_id="conversation-1"),
        tenant_context=tenant_context,
        llm=FakeFinalModel(),
    )

    assert response.answer == "Tenant-safe response."
    assert response.conversation_id == "conversation-1"


def test_chat_body_cannot_override_tenant_context() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {
                "message": "Hello",
                "conversation_id": "conversation-1",
                "tenant_id": str(uuid4()),
            }
        )
