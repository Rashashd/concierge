"""Per-tenant LLM cost attribution."""

from uuid import UUID

import structlog
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import cost_records as cost_repo

logger = structlog.get_logger(__name__)


class TurnCost(BaseModel):
    """Token usage for one agent turn, summed across all LLM calls it made."""

    tenant_id: UUID
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def extract_turn_cost(
    tenant_id: UUID,
    model: str,
    messages: list[BaseMessage],
) -> TurnCost:
    """Sum usage_metadata across every AIMessage produced in a single agent turn.

    In a multi-step turn (tool call → LLM → tool call → LLM) each LLM
    response contributes its own usage_metadata. This sums them all.

    Wiring (Hadi): call this at the end of run_agent_turn() in
    services/agent/graph.py, passing state["messages"] and llm.model_name.
    """
    prompt = 0
    completion = 0
    total = 0
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.usage_metadata:
            prompt += msg.usage_metadata.get("input_tokens", 0)
            completion += msg.usage_metadata.get("output_tokens", 0)
            total += msg.usage_metadata.get("total_tokens", 0)
    return TurnCost(
        tenant_id=tenant_id,
        model=model,
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
    )


async def record_turn_cost(session: AsyncSession, cost: TurnCost) -> None:
    """Persist token usage for one agent turn."""
    await cost_repo.create(
        session,
        tenant_id=cost.tenant_id,
        model=cost.model,
        prompt_tokens=cost.prompt_tokens,
        completion_tokens=cost.completion_tokens,
        total_tokens=cost.total_tokens,
    )
    logger.info(
        "cost.turn_recorded",
        tenant_id=str(cost.tenant_id),
        model=cost.model,
        total_tokens=cost.total_tokens,
    )
