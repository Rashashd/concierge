from typing import Annotated, Any

from fastapi import APIRouter, Depends

from app.core.dependencies import get_current_tenant, get_llm_client, get_redis
from app.schemas import ChatRequest, ChatResponse, TenantContext
from app.services.agent.graph import run_agent_turn
from app.services.memory import RedisMemoryClient, load_history, save_turn

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    tenant_context: Annotated[TenantContext, Depends(get_current_tenant)],
    llm: Annotated[Any, Depends(get_llm_client)],
    redis: Annotated[RedisMemoryClient, Depends(get_redis)],
) -> ChatResponse:
    history = await load_history(
        redis=redis,
        tenant_id=tenant_context.tenant_id,
        session_id=tenant_context.session_id,
    )
    answer = await run_agent_turn(
        llm=llm,
        tenant_context=tenant_context,
        message=request.message,
        conversation_id=request.conversation_id,
        memory_messages=history,
    )
    await save_turn(
        redis=redis,
        tenant_id=tenant_context.tenant_id,
        session_id=tenant_context.session_id,
        user_message=request.message,
        assistant_message=answer,
    )
    return ChatResponse(answer=answer, conversation_id=request.conversation_id)
