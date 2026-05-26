from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage

from app.schemas import TenantContext
from app.services.agent.graph import run_agent_turn


class FakeToolCallingModel:
    def __init__(self) -> None:
        self.calls = 0

    def bind_tools(self, tools: object) -> "FakeToolCallingModel":
        return self

    async def ainvoke(self, messages: object) -> AIMessage:
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "rag_search",
                        "args": {"query": "What are your hours?", "top_k": 3},
                        "id": "call_1",
                    }
                ],
            )
        return AIMessage(content="We are open during posted business hours.")


@pytest.mark.asyncio
async def test_agent_runs_tool_call_then_final_answer() -> None:
    tenant_context = TenantContext(
        tenant_id=uuid4(),
        widget_id=uuid4(),
        session_id="session-1",
    )

    answer = await run_agent_turn(
        llm=FakeToolCallingModel(),
        tenant_context=tenant_context,
        message="What are your hours?",
        conversation_id="conversation-1",
    )

    assert answer == "We are open during posted business hours."
