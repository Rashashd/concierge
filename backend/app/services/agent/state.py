from typing import TypedDict

from langchain_core.messages import BaseMessage

from app.schemas import TenantContext


class AgentState(TypedDict):
    messages: list[BaseMessage]
    tenant_context: TenantContext
    conversation_id: str | None
