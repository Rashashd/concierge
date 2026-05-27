from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from app.schemas import TenantContext
from app.services.agent.nodes import llm_node, tool_node
from app.services.agent.state import AgentState
from app.services.memory import MemoryMessage

if TYPE_CHECKING:
    from app.services.rag import RAGService

MAX_AGENT_STEPS = 4


def _next_step(state: AgentState) -> str:
    messages = state["messages"]
    last_message = messages[-1]
    if len(messages) >= MAX_AGENT_STEPS:
        return "final"
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "final"


def build_agent_graph(llm: Any) -> Any:
    graph = StateGraph(AgentState)

    async def call_llm(state: AgentState) -> dict[str, list[BaseMessage]]:
        return await llm_node(state, llm)

    graph.add_node("llm", call_llm)
    graph.add_node("tools", tool_node)
    graph.add_node("final", lambda state: state)
    graph.set_entry_point("llm")
    graph.add_conditional_edges("llm", _next_step, {"tools": "tools", "final": "final"})
    graph.add_edge("tools", "llm")
    graph.add_edge("final", END)
    return graph.compile()


async def run_agent_turn(
    llm: Any,
    tenant_context: TenantContext,
    message: str,
    conversation_id: str | None,
    memory_messages: Sequence[MemoryMessage] | None = None,
    rag_service: RAGService | None = None,
) -> str:
    state: AgentState = {
        "messages": [
            SystemMessage(
                content=(
                    "You are Concierge. Use rag_search for tenant CMS questions. "
                    "Never ask for or invent tenant IDs."
                )
            ),
            *_to_langchain_messages(memory_messages or []),
            HumanMessage(content=message),
        ],
        "tenant_context": tenant_context,
        "conversation_id": conversation_id,
        "rag_service": rag_service,
    }

    for _ in range(MAX_AGENT_STEPS):
        state["messages"] = (await llm_node(state, llm))["messages"]
        last_message = state["messages"][-1]
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            break
        state["messages"] = (await tool_node(state))["messages"]

    return _final_text(state["messages"])


def _final_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            content = message.content
            if isinstance(content, str):
                return content
            return str(content)
    return "I could not generate a response."


def _to_langchain_messages(messages: Sequence[MemoryMessage]) -> list[BaseMessage]:
    converted: list[BaseMessage] = []
    for message in messages:
        if message.role == "user":
            converted.append(HumanMessage(content=message.content))
        else:
            converted.append(AIMessage(content=message.content))
    return converted
