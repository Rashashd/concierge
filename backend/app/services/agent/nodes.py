import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import StructuredTool

from app.schemas import RAGSearchInput, ToolError
from app.services.agent.state import AgentState
from app.tools.rag_search import TOOL_NAME, rag_search


async def _rag_search_tool(query: str, top_k: int = 5) -> str:
    """LLM-visible schema only. The graph injects tenant_id at runtime."""

    return f"Search for {query} with top_k={top_k}"


RAG_SEARCH_TOOL = StructuredTool.from_function(
    coroutine=_rag_search_tool,
    name=TOOL_NAME,
    description="Search tenant CMS content for information relevant to the visitor.",
    args_schema=RAGSearchInput,
)

TOOLS = [RAG_SEARCH_TOOL]


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

        if tool_name != TOOL_NAME:
            content = ToolError(
                tool=tool_name,
                code="unknown_tool",
                message="The requested tool is not available.",
            ).model_dump_json()
        else:
            content = await _run_rag_search(state, tool_call["args"])

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
            tool=TOOL_NAME,
            code="validation_error",
            message=str(exc),
        ).model_dump_json()

    result = await rag_search(
        tenant_id=state["tenant_context"].tenant_id,
        tool_input=tool_input,
    )
    return json.dumps(result.model_dump(mode="json"))
