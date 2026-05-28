from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.dependencies import (
    get_classifier_client,
    get_current_tenant,
    get_embeddings_client,
    get_llm_client,
    get_redis,
    get_reranker,
    get_tenant_session,
)
from app.schemas import ChatRequest, ChatResponse, TenantContext
from app.services.agent.graph import run_agent_turn
from app.services.classifier_router import (
    ClassifierClient,
    resolve_chat_answer,
)
from app.services.memory import RedisMemoryClient, load_history, save_turn
from app.services.rag import build_pgvector_rag_service
from app.services.reranker import Reranker

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    tenant_context: Annotated[TenantContext, Depends(get_current_tenant)],
    llm: Annotated[Any, Depends(get_llm_client)],
    redis: Annotated[RedisMemoryClient, Depends(get_redis)],
    session: Annotated[AsyncSession, Depends(get_tenant_session)],
    embeddings: Annotated[Any, Depends(get_embeddings_client)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
    settings: Annotated[Settings, Depends(get_settings)],
    classifier: Annotated[
        ClassifierClient | None, Depends(get_classifier_client)
    ],
) -> ChatResponse:
    history = await load_history(
        redis=redis,
        tenant_id=tenant_context.tenant_id,
        session_id=tenant_context.session_id,
    )

    async def _run_rag_agent() -> str:
        rag_service = build_pgvector_rag_service(
            session=session,
            embeddings_client=embeddings,
            reranker=reranker,
            retrieval_mode=settings.rag_retrieval_mode,
            hybrid_vector_weight=settings.hybrid_vector_weight,
            hybrid_keyword_weight=settings.hybrid_keyword_weight,
            hybrid_vector_candidate_count=settings.hybrid_vector_candidate_count,
            hybrid_keyword_candidate_count=settings.hybrid_keyword_candidate_count,
        )
        return await run_agent_turn(
            llm=llm,
            tenant_context=tenant_context,
            message=request.message,
            conversation_id=request.conversation_id,
            memory_messages=history,
            rag_service=rag_service,
        )

    answer, route = await resolve_chat_answer(
        classifier=classifier,
        message=request.message,
        run_agent=_run_rag_agent,
    )

    if route.action != "refuse":
        await save_turn(
            redis=redis,
            tenant_id=tenant_context.tenant_id,
            session_id=tenant_context.session_id,
            user_message=request.message,
            assistant_message=answer,
        )
    return ChatResponse(answer=answer, conversation_id=request.conversation_id)
