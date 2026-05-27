from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_tenant,
    get_embeddings_client,
    get_llm_client,
    get_redis,
    get_tenant_session,
)
from app.schemas import ChatRequest, ChatResponse, TenantContext
from app.services.agent.graph import run_agent_turn
from app.services.memory import RedisMemoryClient, load_history, save_turn
from app.services.rag import build_pgvector_rag_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    tenant_context: Annotated[TenantContext, Depends(get_current_tenant)],
    llm: Annotated[Any, Depends(get_llm_client)],
    redis: Annotated[RedisMemoryClient, Depends(get_redis)],
    session: Annotated[AsyncSession, Depends(get_tenant_session)],
    embeddings: Annotated[Any, Depends(get_embeddings_client)],
) -> ChatResponse:
    history = await load_history(
        redis=redis,
        tenant_id=tenant_context.tenant_id,
        session_id=tenant_context.session_id,
    )
    rag_service = build_pgvector_rag_service(
        session=session,
        embeddings_client=embeddings,
    )
    answer = await run_agent_turn(
        llm=llm,
        tenant_context=tenant_context,
        message=request.message,
        conversation_id=request.conversation_id,
        memory_messages=history,
        rag_service=rag_service,
    )
    await save_turn(
        redis=redis,
        tenant_id=tenant_context.tenant_id,
        session_id=tenant_context.session_id,
        user_message=request.message,
        assistant_message=answer,
    )
    return ChatResponse(answer=answer, conversation_id=request.conversation_id)
