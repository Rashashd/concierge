from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict

from langchain_core.messages import BaseMessage

from app.schemas import TenantContext

if TYPE_CHECKING:
    from app.services.rag import RAGService


class AgentState(TypedDict):
    messages: list[BaseMessage]
    tenant_context: TenantContext
    conversation_id: str | None
    rag_service: NotRequired[RAGService | None]
