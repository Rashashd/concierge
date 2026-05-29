import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import SecretStr

from app.api.chat import chat
from app.core.config import Settings
from app.infra.guardrails import GuardrailResponse
from app.schemas import ChatRequest, TenantContext
from app.services.classifier_router import (
    REFUSE_MESSAGE,
    ClassifierPrediction,
    ClassifierScores,
)
from app.services.memory import build_session_key


class FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


class FakeRedactor:
    def redact(self, text: str) -> str:
        return text


class FakeGuardrails:
    async def check_input(
        self,
        tenant_id: object,
        message: str,
        tenant_config: object = None,
    ) -> GuardrailResponse:
        return GuardrailResponse(decision="allow")

    async def check_output(
        self,
        tenant_id: object,
        message: str,
        tenant_config: object = None,
    ) -> GuardrailResponse:
        return GuardrailResponse(decision="allow")


class FakeLLM:
    def __init__(self) -> None:
        self.received_messages: list[BaseMessage] = []

    def bind_tools(self, tools: object) -> "FakeLLM":
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.received_messages = messages
        return AIMessage(content="Tenant-safe response.")


class FakeRedis:
    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}

    async def rpush(self, name: str, *values: str) -> int:
        self.lists.setdefault(name, []).extend(values)
        return len(self.lists[name])

    async def expire(self, name: str, time: int) -> bool:
        return True

    async def lrange(self, name: str, start: int, end: int) -> list[str]:
        values = self.lists.get(name, [])
        if start < 0:
            start = max(len(values) + start, 0)
        if end < 0:
            end = len(values) + end
        return values[start : end + 1]


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


def _fake_tenant() -> object:
    return type(
        "FakeTenant",
        (),
        {"allowed_origins": [], "guardrail_config": {}},
    )()


def _base_deps() -> dict:
    return {
        "http_request": FakeRequest(),
        "request": ChatRequest(
            message="What are your store hours?", conversation_id="conv-1"
        ),
        "tenant_context": TenantContext(
            tenant_id=uuid4(),
            widget_id=uuid4(),
            session_id="session-1",
        ),
        "llm": FakeLLM(),
        "redis": FakeRedis(),
        "session": object(),
        "embeddings": object(),
        "reranker": None,
        "redactor": FakeRedactor(),
        "settings": Settings(
            vault_addr="http://vault:8200", vault_token=SecretStr("x")
        ),
        "guardrails": FakeGuardrails(),
    }


@pytest.fixture
def _patch_tenant_repo():
    with patch(
        "app.api.chat.tenant_repo.get_by_id",
        AsyncMock(return_value=_fake_tenant()),
    ):
        yield


@pytest.mark.asyncio
async def test_smoke_full_agent_pipeline(_patch_tenant_repo: None) -> None:
    """Classifier→agent→LLM→memory: full pipeline integration."""
    deps = _base_deps()
    prediction = _make_prediction("question", "rag_search")

    class SmokeClassifier:
        def __init__(self) -> None:
            self.called = False

        async def predict(self, message: str) -> ClassifierPrediction:
            self.called = True
            return prediction

    classifier = SmokeClassifier()
    response = await chat(classifier=classifier, **deps)  # type: ignore[arg-type]

    assert classifier.called
    assert response.answer == "Tenant-safe response."
    assert response.conversation_id == "conv-1"
    assert deps["llm"].received_messages

    key = build_session_key(
        deps["tenant_context"].tenant_id,
        deps["tenant_context"].session_id,
    )
    assert key.startswith("session:")
    assert key.endswith(":session-1")
    assert str(deps["tenant_context"].tenant_id) in key

    assert len(deps["redis"].lists[key]) == 2
    saved = [json.loads(m) for m in deps["redis"].lists[key]]
    assert saved[0] == {"role": "user", "content": "What are your store hours?"}
    assert saved[1] == {"role": "assistant", "content": "Tenant-safe response."}


@pytest.mark.asyncio
async def test_smoke_spam_pipeline_no_llm_no_memory(
    _patch_tenant_repo: None,
) -> None:
    """Spam classifier → refuse, no LLM call, no memory stored."""
    deps = _base_deps()
    prediction = _make_prediction("spam", "drop")

    class SpamClassifier:
        def __init__(self) -> None:
            self.called = False

        async def predict(self, message: str) -> ClassifierPrediction:
            self.called = True
            return prediction

    classifier = SpamClassifier()
    response = await chat(classifier=classifier, **deps)  # type: ignore[arg-type]

    assert classifier.called
    assert response.answer == REFUSE_MESSAGE
    assert response.conversation_id == "conv-1"
    assert not deps["llm"].received_messages

    key = build_session_key(
        deps["tenant_context"].tenant_id,
        deps["tenant_context"].session_id,
    )
    assert key not in deps["redis"].lists
