from uuid import uuid4

import pytest
from langchain_core.messages import BaseMessage
from pydantic import SecretStr, ValidationError

from app.api.chat import (
    ESCALATE_MESSAGE,
    LEAD_MESSAGE,
    REFUSE_MESSAGE,
    chat,
)
from app.core.config import Settings
from app.schemas import ChatRequest, TenantContext
from app.services.classifier_router import (
    ClassifierPrediction,
    ClassifierScores,
)
from app.services.memory import build_session_key


class FakeFinalModel:
    def __init__(self) -> None:
        self.received_messages: list[BaseMessage] = []

    def bind_tools(self, tools: object) -> "FakeFinalModel":
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> object:
        from langchain_core.messages import AIMessage

        self.received_messages = messages
        return AIMessage(content="Tenant-safe response.")


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str | bytes]] = {}
        self.ttls: dict[str, int] = {}

    async def rpush(self, name: str, *values: str) -> int:
        self.lists.setdefault(name, []).extend(values)
        return len(self.lists[name])

    async def expire(self, name: str, time: int) -> bool:
        self.ttls[name] = time
        return True

    async def lrange(self, name: str, start: int, end: int) -> list[str | bytes]:
        values = self.lists.get(name, [])
        if start < 0:
            start = max(len(values) + start, 0)
        if end < 0:
            end = len(values) + end
        return values[start : end + 1]

    async def scan(
        self,
        cursor: int = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[str | bytes]]:
        return 0, []

    async def delete(self, *names: str) -> int:
        return 0


def _make_prediction(
    label: str = "question",
    route_hint: str = "rag_search",
    confidence: float = 0.95,
) -> ClassifierPrediction:
    scores = ClassifierScores(spam=0.0, question=0.0, lead=0.0, escalate=0.0)
    setattr(scores, label, confidence)
    return ClassifierPrediction(
        label=label,
        confidence=confidence,
        scores=scores,
        model_version="1.0.0",
        route_hint=route_hint,
    )


def _base_deps():
    """Return the base deps dict shared by most tests."""
    return {
        "request": ChatRequest(message="Hello", conversation_id="conversation-1"),
        "tenant_context": TenantContext(
            tenant_id=uuid4(),
            widget_id=uuid4(),
            session_id="session-1",
        ),
        "llm": FakeFinalModel(),
        "redis": FakeRedis(),
        "session": object(),
        "embeddings": object(),
        "reranker": None,
        "settings": Settings(
            vault_addr="http://vault:8200", vault_token=SecretStr("x")
        ),
    }


@pytest.mark.asyncio
async def test_chat_returns_agent_response_with_verified_tenant_context() -> None:
    deps = _base_deps()
    response = await chat(classifier=None, **deps)  # type: ignore[arg-type]

    assert response.answer == "Tenant-safe response."
    assert response.conversation_id == "conversation-1"
    key = build_session_key(
        deps["tenant_context"].tenant_id, deps["tenant_context"].session_id
    )
    assert len(deps["redis"].lists[key]) == 2


@pytest.mark.asyncio
async def test_chat_loads_tenant_scoped_history_before_agent_turn() -> None:
    deps = _base_deps()
    key = build_session_key(
        deps["tenant_context"].tenant_id, deps["tenant_context"].session_id
    )
    deps["redis"].lists[key] = [
        '{"role":"user","content":"Earlier question"}',
        '{"role":"assistant","content":"Earlier answer"}',
    ]

    await chat(classifier=None, **deps)  # type: ignore[arg-type]

    contents = [str(message.content) for message in deps["llm"].received_messages]
    assert contents == [
        "You are Concierge. Use rag_search for tenant CMS questions. "
        "Never ask for or invent tenant IDs.",
        "Earlier question",
        "Earlier answer",
        "Hello",
    ]


def test_chat_body_cannot_override_tenant_context() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {
                "message": "Hello",
                "conversation_id": "conversation-1",
                "tenant_id": str(uuid4()),
            }
        )


# ── Classifier routing tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spam_route_does_not_call_llm() -> None:
    deps = _base_deps()
    prediction = _make_prediction("spam", "drop")

    class FakeSpamClassifier:
        def __init__(self) -> None:
            self.called = False

        async def predict(self, message: str) -> ClassifierPrediction:
            self.called = True
            return prediction

    classifier = FakeSpamClassifier()
    response = await chat(classifier=classifier, **deps)  # type: ignore[arg-type]

    assert classifier.called is True
    assert response.answer == REFUSE_MESSAGE
    assert not deps["llm"].received_messages


@pytest.mark.asyncio
async def test_spam_route_saves_memory() -> None:
    deps = _base_deps()
    prediction = _make_prediction("spam", "drop")

    class FakeSpamClassifier:
        async def predict(self, message: str) -> ClassifierPrediction:
            return prediction

    response = await chat(classifier=FakeSpamClassifier(), **deps)  # type: ignore[arg-type]

    assert response.answer == REFUSE_MESSAGE
    key = build_session_key(
        deps["tenant_context"].tenant_id, deps["tenant_context"].session_id
    )
    assert len(deps["redis"].lists[key]) == 2


@pytest.mark.asyncio
async def test_classifier_failure_falls_back_to_agent() -> None:
    deps = _base_deps()

    class FailingClassifier:
        async def predict(self, message: str) -> ClassifierPrediction:
            raise RuntimeError("model-server timeout")

    response = await chat(classifier=FailingClassifier(), **deps)  # type: ignore[arg-type]

    assert response.answer == "Tenant-safe response."
    assert deps["llm"].received_messages


@pytest.mark.asyncio
async def test_question_route_preserves_agent_behavior() -> None:
    deps = _base_deps()
    prediction = _make_prediction("question", "rag_search")

    class QuestionClassifier:
        async def predict(self, message: str) -> ClassifierPrediction:
            return prediction

    response = await chat(classifier=QuestionClassifier(), **deps)  # type: ignore[arg-type]

    assert response.answer == "Tenant-safe response."
    assert deps["llm"].received_messages
    key = build_session_key(
        deps["tenant_context"].tenant_id, deps["tenant_context"].session_id
    )
    assert len(deps["redis"].lists[key]) == 2


@pytest.mark.asyncio
async def test_lead_route_returns_lead_response() -> None:
    deps = _base_deps()
    prediction = _make_prediction("lead", "capture_lead")

    class LeadClassifier:
        async def predict(self, message: str) -> ClassifierPrediction:
            return prediction

    response = await chat(classifier=LeadClassifier(), **deps)  # type: ignore[arg-type]

    assert response.answer == LEAD_MESSAGE
    assert not deps["llm"].received_messages


@pytest.mark.asyncio
async def test_escalate_route_returns_escalate_response() -> None:
    deps = _base_deps()
    prediction = _make_prediction("escalate", "escalate")

    class EscalateClassifier:
        async def predict(self, message: str) -> ClassifierPrediction:
            return prediction

    response = await chat(classifier=EscalateClassifier(), **deps)  # type: ignore[arg-type]

    assert response.answer == ESCALATE_MESSAGE
    assert not deps["llm"].received_messages


@pytest.mark.asyncio
async def test_none_classifier_runs_normal_agent() -> None:
    deps = _base_deps()
    response = await chat(classifier=None, **deps)  # type: ignore[arg-type]

    assert response.answer == "Tenant-safe response."
    assert deps["llm"].received_messages


@pytest.mark.asyncio
async def test_agent_handoff_runs_normal_agent() -> None:
    deps = _base_deps()
    prediction = _make_prediction("lead", "agent_handoff", confidence=0.30)

    class HandoffClassifier:
        async def predict(self, message: str) -> ClassifierPrediction:
            return prediction

    response = await chat(classifier=HandoffClassifier(), **deps)  # type: ignore[arg-type]

    assert response.answer == "Tenant-safe response."
    assert deps["llm"].received_messages
