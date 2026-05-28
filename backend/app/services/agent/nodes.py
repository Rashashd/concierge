import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import StructuredTool

from app.schemas import (
    CaptureLeadInput,
    EscalateInput,
    RAGSearchInput,
    ToolError,
)
from app.services.agent.state import AgentState
from app.tools.capture_lead import TOOL_NAME as CAPTURE_LEAD_TOOL_NAME
from app.tools.capture_lead import capture_lead
from app.tools.escalate import TOOL_NAME as ESCALATE_TOOL_NAME
from app.tools.escalate import escalate
from app.tools.rag_search import TOOL_NAME as RAG_TOOL_NAME
from app.tools.rag_search import rag_search


async def _rag_search_tool(query: str, top_k: int = 5) -> str:
    """LLM-visible schema only. The graph injects tenant_id at runtime."""

    return f"Search for {query} with top_k={top_k}"


async def _capture_lead_tool(
    visitor_name: str | None = None,
    contact: str = "",
    intent: str = "",
    session_id: str = "",
) -> str:
    """LLM-visible schema. Tenant_id and DB session injected by graph."""

    return "Lead capture requested."


async def _escalate_tool(reason: str = "", conversation_id: str = "") -> str:
    """LLM-visible schema. Tenant_id and DB session injected by graph."""

    return "Escalation requested."


RAG_SEARCH_TOOL = StructuredTool.from_function(
    coroutine=_rag_search_tool,
    name=RAG_TOOL_NAME,
    description="Search tenant CMS content for information relevant to the visitor.",
    args_schema=RAGSearchInput,
)

CAPTURE_LEAD_TOOL = StructuredTool.from_function(
    coroutine=_capture_lead_tool,
    name=CAPTURE_LEAD_TOOL_NAME,
    description="Capture a visitor's contact information as a lead for follow-up.",
    args_schema=CaptureLeadInput,
)

ESCALATE_TOOL = StructuredTool.from_function(
    coroutine=_escalate_tool,
    name=ESCALATE_TOOL_NAME,
    description="Escalate the conversation to a human team member.",
    args_schema=EscalateInput,
)

TOOLS = [RAG_SEARCH_TOOL, CAPTURE_LEAD_TOOL, ESCALATE_TOOL]


async def llm_node(state: AgentState, llm: Any) -> dict[str, list[BaseMessage]]:
    model = llm.bind_tools(TOOLS)
    response = await model.ainvoke(state["messages"])
    return {"messages": [*state["messages"], response]}


async def tool_node(state: AgentState) -> dict[str, list[BaseMessage]]:
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {"messages": state["messages"]}

    tool_messages: list[ToolMessage] = []
    for tool_call in last_message.tool_calls:
        tool_name = str(tool_call["name"])
        tool_call_id = str(tool_call["id"])

        if tool_name == RAG_TOOL_NAME:
            content = await _run_rag_search(state, tool_call["args"])
        elif tool_name == CAPTURE_LEAD_TOOL_NAME:
            content = await _run_capture_lead(state, tool_call["args"])
        elif tool_name == ESCALATE_TOOL_NAME:
            content = await _run_escalate(state, tool_call["args"])
        else:
            content = ToolError(
                tool=tool_name,
                code="unknown_tool",
                message="The requested tool is not available.",
            ).model_dump_json()

        tool_messages.append(
            ToolMessage(
                content=content,
                name=tool_name,
                tool_call_id=tool_call_id,
            )
        )

    return {"messages": [*state["messages"], *tool_messages]}


async def _run_rag_search(state: AgentState, args: dict[str, Any]) -> str:
    try:
        tool_input = RAGSearchInput.model_validate(args)
    except ValueError as exc:
        return ToolError(
            tool=RAG_TOOL_NAME,
            code="validation_error",
            message=str(exc),
        ).model_dump_json()

    result = await rag_search(
        tenant_id=state["tenant_context"].tenant_id,
        tool_input=tool_input,
        rag_service=state.get("rag_service"),
    )
    return json.dumps(result.model_dump(mode="json"))


async def _run_capture_lead(state: AgentState, args: dict[str, Any]) -> str:
    try:
        tool_input = CaptureLeadInput.model_validate(args)
    except ValueError as exc:
        return ToolError(
            tool=CAPTURE_LEAD_TOOL_NAME,
            code="validation_error",
            message=str(exc),
        ).model_dump_json()

    result = await capture_lead(
        tenant_id=state["tenant_context"].tenant_id,
        tool_input=tool_input,
        session=state.get("session"),
    )
    return json.dumps(result.model_dump(mode="json"))


async def _run_escalate(state: AgentState, args: dict[str, Any]) -> str:
    try:
        tool_input = EscalateInput.model_validate(args)
    except ValueError as exc:
        return ToolError(
            tool=ESCALATE_TOOL_NAME,
            code="validation_error",
            message=str(exc),
        ).model_dump_json()

    result = await escalate(
        tenant_id=state["tenant_context"].tenant_id,
        tool_input=tool_input,
        session=state.get("session"),
    )
    return json.dumps(result.model_dump(mode="json"))
