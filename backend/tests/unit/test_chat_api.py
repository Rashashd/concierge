from uuid import uuid4

import pytest
from langchain_core.messages import BaseMessage
from pydantic import ValidationError

from app.api.chat import chat
from app.schemas import ChatRequest, TenantContext
from app.services.memory import build_session_key


class FakeFinalModel:
    def __init__(self) -> None:
        self.received_messages: list[BaseMessage] = []

    def bind_tools(self, tools: object) -> "FakeFinalModel":
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> object:
        from langchain_core.messages import AIMessage

        self.received_messages = messages
        return AIMessage(content="Tenant-safe response.")


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str | bytes]] = {}
        self.ttls: dict[str, int] = {}

    async def rpush(self, name: str, *values: str) -> int:
        self.lists.setdefault(name, []).extend(values)
        return len(self.lists[name])

    async def expire(self, name: str, time: int) -> bool:
        self.ttls[name] = time
        return True

    async def lrange(self, name: str, start: int, end: int) -> list[str | bytes]:
        values = self.lists.get(name, [])
        if start < 0:
            start = max(len(values) + start, 0)
        if end < 0:
            end = len(values) + end
        return values[start : end + 1]

    async def scan(
        self,
        cursor: int = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[str | bytes]]:
        return 0, []

    async def delete(self, *names: str) -> int:
        return 0


@pytest.mark.asyncio
async def test_chat_returns_agent_response_with_verified_tenant_context() -> None:
    tenant_context = TenantContext(
        tenant_id=uuid4(),
        widget_id=uuid4(),
        session_id="session-1",
    )
    redis = FakeRedis()
    model = FakeFinalModel()
    response = await chat(
        request=ChatRequest(message="Hello", conversation_id="conversation-1"),
        tenant_context=tenant_context,
        llm=model,
        redis=redis,
    )

    assert response.answer == "Tenant-safe response."
    assert response.conversation_id == "conversation-1"
    key = build_session_key(tenant_context.tenant_id, tenant_context.session_id)
    assert len(redis.lists[key]) == 2


@pytest.mark.asyncio
async def test_chat_loads_tenant_scoped_history_before_agent_turn() -> None:
    tenant_context = TenantContext(
        tenant_id=uuid4(),
        widget_id=uuid4(),
        session_id="session-1",
    )
    redis = FakeRedis()
    key = build_session_key(tenant_context.tenant_id, tenant_context.session_id)
    redis.lists[key] = [
        '{"role":"user","content":"Earlier question"}',
        '{"role":"assistant","content":"Earlier answer"}',
    ]
    model = FakeFinalModel()

    await chat(
        request=ChatRequest(message="Current question"),
        tenant_context=tenant_context,
        llm=model,
        redis=redis,
    )

    contents = [str(message.content) for message in model.received_messages]
    assert contents == [
        "You are Concierge. Use rag_search for tenant CMS questions. "
        "Never ask for or invent tenant IDs.",
        "Earlier question",
        "Earlier answer",
        "Current question",
    ]


def test_chat_body_cannot_override_tenant_context() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {
                "message": "Hello",
                "conversation_id": "conversation-1",
                "tenant_id": str(uuid4()),
            }
        )
