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
    route_conversation,
)
from app.services.memory import RedisMemoryClient, load_history, save_turn
from app.services.rag import build_pgvector_rag_service
from app.services.reranker import Reranker

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

REFUSE_MESSAGE = (
    "I'm sorry, but I can't help with that request. "
    "Please try again with a different question."
)

LEAD_MESSAGE = (
    "I'd love to help! Could you share your contact details "
    "and a brief description of what you need?"
)

ESCALATE_MESSAGE = (
    "This might need a human touch. Please leave your contact info "
    "and a summary of your issue, and someone will reach out shortly."
)


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

    prediction = None
    if classifier is not None:
        try:
            prediction = await classifier.predict(request.message)
        except Exception:
            logger.warning("classifier_unavailable")

    route = route_conversation(prediction)

    if route.action == "refuse":
        answer = REFUSE_MESSAGE
    elif route.action == "lead":
        answer = LEAD_MESSAGE
    elif route.action == "escalate":
        answer = ESCALATE_MESSAGE
    else:
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
