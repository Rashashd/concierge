from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.dependencies import (
    get_classifier_client,
    get_current_tenant,
    get_embeddings_client,
    get_guardrails_client,
    get_llm_client,
    get_redactor,
    get_redis,
    get_reranker,
    get_tenant_session,
)
from app.infra.guardrails import GuardrailsClient
from app.repositories import tenants as tenant_repo
from app.schemas import ChatRequest, ChatResponse, TenantContext
from app.security.origin import is_origin_allowed
from app.security.redaction import Redactor
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
    http_request: Request,
    request: ChatRequest,
    tenant_context: Annotated[TenantContext, Depends(get_current_tenant)],
    llm: Annotated[Any, Depends(get_llm_client)],
    redis: Annotated[RedisMemoryClient, Depends(get_redis)],
    session: Annotated[AsyncSession, Depends(get_tenant_session)],
    embeddings: Annotated[Any, Depends(get_embeddings_client)],
    reranker: Annotated[Reranker, Depends(get_reranker)],
    redactor: Annotated[Redactor, Depends(get_redactor)],
    settings: Annotated[Settings, Depends(get_settings)],
    classifier: Annotated[
        ClassifierClient | None, Depends(get_classifier_client)
    ],
    guardrails: Annotated[GuardrailsClient, Depends(get_guardrails_client)],
) -> ChatResponse:
    tenant = await tenant_repo.get_by_id(session, tenant_context.tenant_id)
    origin = http_request.headers.get("origin")
    allowed_origins = tenant.allowed_origins if tenant else []
    if not is_origin_allowed(origin, allowed_origins):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed",
        )

    safe_message = redactor.redact(request.message)
    tenant_guardrail_config: dict = tenant.guardrail_config if tenant else {}

    try:
        input_check = await guardrails.check_input(
            tenant_id=tenant_context.tenant_id,
            message=safe_message,
            tenant_config=tenant_guardrail_config,
        )
        if input_check.decision == "refuse":
            return ChatResponse(
                answer=input_check.reason
                or "I'm sorry, I can't help with that request.",
                conversation_id=request.conversation_id,
            )
    except Exception as exc:
        logger.warning("guardrails.check_input_failed", error_type=type(exc).__name__)

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
            message=safe_message,
            conversation_id=request.conversation_id,
            memory_messages=history,
            rag_service=rag_service,
            session=session,
        )

    answer, route = await resolve_chat_answer(
        classifier=classifier,
        message=safe_message,
        run_agent=_run_rag_agent,
    )

    try:
        output_check = await guardrails.check_output(
            tenant_id=tenant_context.tenant_id,
            message=answer,
            tenant_config=tenant_guardrail_config,
        )
        if output_check.decision == "allow" and output_check.safe_text:
            answer = output_check.safe_text
        elif output_check.decision == "refuse":
            answer = "I'm sorry, I'm unable to provide that response."
    except Exception as exc:
        logger.warning("guardrails.check_output_failed", error_type=type(exc).__name__)

    if route.action != "refuse":
        await save_turn(
            redis=redis,
            tenant_id=tenant_context.tenant_id,
            session_id=tenant_context.session_id,
            user_message=safe_message,
            assistant_message=answer,
        )
    return ChatResponse(answer=answer, conversation_id=request.conversation_id)
