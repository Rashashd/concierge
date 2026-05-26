from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_tenant, get_llm_client
from app.schemas import ChatRequest, ChatResponse, TenantContext
from app.services.agent.graph import run_agent_turn

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    tenant_context: Annotated[TenantContext, Depends(get_current_tenant)],
    llm: Annotated[Any, Depends(get_llm_client)],
) -> ChatResponse:
    answer = await run_agent_turn(
        llm=llm,
        tenant_context=tenant_context,
        message=request.message,
        conversation_id=request.conversation_id,
    )
    return ChatResponse(answer=answer, conversation_id=request.conversation_id)
