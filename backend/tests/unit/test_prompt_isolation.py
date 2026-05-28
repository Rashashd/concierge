"""Assert the system prompt includes tenant isolation guardrails."""

from uuid import uuid4

import pytest
from langchain_core.messages import SystemMessage

from app.schemas import TenantContext
from app.services.agent.graph import run_agent_turn


class CapturingLLM:
    def __init__(self) -> None:
        self.system_content: str = ""

    def bind_tools(self, tools: object) -> "CapturingLLM":
        return self

    async def ainvoke(self, messages: list) -> object:
        from langchain_core.messages import AIMessage

        for msg in messages:
            if isinstance(msg, SystemMessage):
                self.system_content = str(msg.content)
                break
        return AIMessage(content="ok")


@pytest.mark.asyncio
async def test_system_prompt_contains_tenant_isolation_keywords() -> None:
    llm = CapturingLLM()
    await run_agent_turn(
        llm=llm,
        tenant_context=TenantContext(
            tenant_id=uuid4(),
            widget_id=uuid4(),
            session_id="session-1",
        ),
        message="hello",
        conversation_id="conv-1",
    )

    prompt = llm.system_content.lower()
    assert "tenant" in prompt, f"missing 'tenant', got: {prompt}"
    assert "verified" in prompt, f"missing 'verified', got: {prompt}"
    assert "ignore" in prompt, f"missing 'ignore', got: {prompt}"
    assert "user" in prompt, f"missing 'user', got: {prompt}"
