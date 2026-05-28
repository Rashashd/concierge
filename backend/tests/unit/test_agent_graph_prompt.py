from uuid import uuid4

import pytest

from app.schemas import TenantContext
from app.services.agent.graph import SYSTEM_PROMPT, run_agent_turn


class SingleCallModel:
    def __init__(self) -> None:
        self.calls = 0
        self.received_messages: list = []

    def bind_tools(self, tools: object) -> "SingleCallModel":
        return self

    async def ainvoke(self, messages: list) -> object:
        from langchain_core.messages import AIMessage

        self.calls += 1
        self.received_messages = messages
        return AIMessage(content="I'm here to help.")


@pytest.mark.asyncio
async def test_system_prompt_loaded_from_file() -> None:
    assert len(SYSTEM_PROMPT) > 50
    assert "Concierge" in SYSTEM_PROMPT
    assert "tenant context" in SYSTEM_PROMPT.lower()
    assert "rag_search" in SYSTEM_PROMPT
    assert "capture_lead" in SYSTEM_PROMPT
    assert "escalate" in SYSTEM_PROMPT
    assert "verified" in SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_run_agent_turn_uses_prompt_from_file() -> None:
    tenant_context = TenantContext(
        tenant_id=uuid4(),
        widget_id=uuid4(),
        session_id="session-1",
    )
    model = SingleCallModel()

    await run_agent_turn(
        llm=model,
        tenant_context=tenant_context,
        message="Hello",
        conversation_id="conv-1",
    )

    first = model.received_messages[0]
    assert "Concierge" in str(first.content)
    assert "rag_search" in str(first.content)
    assert "capture_lead" in str(first.content)
