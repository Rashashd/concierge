from collections.abc import Awaitable, Callable
from typing import Literal, Protocol

import structlog
from pydantic import BaseModel, ConfigDict

logger = structlog.get_logger(__name__)

# ── Messages ─────────────────────────────────────────────────────────────────

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

# ── Models ───────────────────────────────────────────────────────────────────


class ClassifierScores(BaseModel):
    spam: float = 0.0
    question: float = 0.0
    lead: float = 0.0
    escalate: float = 0.0

    model_config = ConfigDict(extra="forbid")


class ClassifierPrediction(BaseModel):
    label: Literal["spam", "question", "lead", "escalate"]
    confidence: float
    scores: ClassifierScores
    model_version: str
    route_hint: Literal[
        "drop", "rag_search", "capture_lead", "escalate", "agent_handoff"
    ]

    model_config = ConfigDict(extra="forbid")


class ConversationRoute(BaseModel):
    action: Literal["refuse", "agent", "lead", "escalate"]
    reason: str
    prediction: ClassifierPrediction | None = None

    model_config = ConfigDict(extra="forbid")


class ClassifierClient(Protocol):
    """Protocol for the model-server classifier HTTP client.

    TODO: Hussein will implement the real client in backend/app/infra/model_server.py.
    The contract is a single async method that takes a visitor message and returns
    a ClassifierPrediction.
    """

    async def predict(self, message: str) -> ClassifierPrediction: ...


# ── Routing ──────────────────────────────────────────────────────────────────


def route_conversation(
    prediction: ClassifierPrediction | None,
) -> ConversationRoute:
    if prediction is None:
        return ConversationRoute(action="agent", reason="classifier_unavailable")

    if prediction.route_hint == "agent_handoff":
        return ConversationRoute(
            action="agent", reason="low_confidence", prediction=prediction
        )

    if prediction.label == "spam" or prediction.route_hint == "drop":
        return ConversationRoute(action="refuse", reason="spam", prediction=prediction)

    if prediction.label == "question" or prediction.route_hint == "rag_search":
        return ConversationRoute(
            action="agent", reason="question", prediction=prediction
        )

    if prediction.label == "lead" or prediction.route_hint == "capture_lead":
        return ConversationRoute(action="lead", reason="lead", prediction=prediction)

    if prediction.label == "escalate" or prediction.route_hint == "escalate":
        return ConversationRoute(
            action="escalate", reason="escalate", prediction=prediction
        )

    return ConversationRoute(action="agent", reason="fallback", prediction=prediction)


# ── Chat answer resolution ───────────────────────────────────────────────────


async def resolve_chat_answer(
    classifier: ClassifierClient | None,
    message: str,
    run_agent: Callable[[], Awaitable[str]],
) -> tuple[str, ConversationRoute]:
    """Resolve a chat message to an answer via classifier routing.

    On classifier failure or unavailability, falls back to agent.
    Returns (answer, route) where route includes the action, reason,
    and optional prediction for observability.
    """
    prediction = None
    if classifier is not None:
        try:
            prediction = await classifier.predict(message)
        except Exception as exc:
            logger.warning("classifier_unavailable", error_type=type(exc).__name__)

    route = route_conversation(prediction)

    if route.action == "refuse":
        return REFUSE_MESSAGE, route
    if route.action == "lead":
        return LEAD_MESSAGE, route
    if route.action == "escalate":
        return ESCALATE_MESSAGE, route

    answer = await run_agent()
    return answer, route
