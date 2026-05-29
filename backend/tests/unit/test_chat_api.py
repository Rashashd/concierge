import json
import re
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import BaseMessage
from pydantic import SecretStr, ValidationError

from app.api.chat import chat
from app.core.config import Settings
from app.infra.guardrails import GuardrailResponse
from app.schemas import ChatRequest, TenantContext
from app.services.agent.graph import SYSTEM_PROMPT
from app.services.classifier_router import (
    ESCALATE_MESSAGE,
    LEAD_MESSAGE,
    REFUSE_MESSAGE,
    ClassifierPrediction,
    ClassifierScores,
)
from app.services.memory import build_session_key


class FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None) -> None:
        self.headers = headers or {}


class FakeRedactor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def redact(self, text: str) -> str:
        self.calls.append(text)
        return text


class FakeGuardrails:
    def __init__(self) -> None:
        self.input_checks: list[tuple] = []
        self.output_checks: list[tuple] = []

    async def check_input(
        self,
        tenant_id: object,
        message: str,
        tenant_config: object = None,
    ) -> GuardrailResponse:
        self.input_checks.append((tenant_id, message, tenant_config))
        return GuardrailResponse(decision="allow")

    async def check_output(
        self,
        tenant_id: object,
        message: str,
        tenant_config: object = None,
    ) -> GuardrailResponse:
        self.output_checks.append((tenant_id, message, tenant_config))
        return GuardrailResponse(decision="allow")


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
        self.lrange_calls: list[tuple] = []

    async def rpush(self, name: str, *values: str) -> int:
        self.lists.setdefault(name, []).extend(values)
        return len(self.lists[name])

    async def expire(self, name: str, time: int) -> bool:
        self.ttls[name] = time
        return True

    async def lrange(self, name: str, start: int, end: int) -> list[str | bytes]:
        self.lrange_calls.append((name, start, end))
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


def _fake_tenant() -> object:
    return type(
        "FakeTenant",
        (),
        {"allowed_origins": [], "guardrail_config": {}},
    )()


def _base_deps():
    """Return the base deps dict shared by most tests."""
    return {
        "http_request": FakeRequest(),
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
async def test_chat_returns_agent_response_with_verified_tenant_context(
    _patch_tenant_repo: None,
) -> None:
    deps = _base_deps()
    response = await chat(classifier=None, **deps)  # type: ignore[arg-type]

    assert response.answer == "Tenant-safe response."
    assert response.conversation_id == "conversation-1"
    key = build_session_key(
        deps["tenant_context"].tenant_id, deps["tenant_context"].session_id
    )
    assert len(deps["redis"].lists[key]) == 2


@pytest.mark.asyncio
async def test_chat_loads_tenant_scoped_history_before_agent_turn(
    _patch_tenant_repo: None,
) -> None:
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
        SYSTEM_PROMPT,
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
async def test_spam_route_does_not_call_llm(_patch_tenant_repo: None) -> None:
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
async def test_spam_route_does_not_save_memory(_patch_tenant_repo: None) -> None:
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
    assert key not in deps["redis"].lists


@pytest.mark.asyncio
async def test_classifier_failure_falls_back_to_agent(
    _patch_tenant_repo: None,
) -> None:
    deps = _base_deps()

    class FailingClassifier:
        async def predict(self, message: str) -> ClassifierPrediction:
            raise RuntimeError("model-server timeout")

    response = await chat(classifier=FailingClassifier(), **deps)  # type: ignore[arg-type]

    assert response.answer == "Tenant-safe response."
    assert deps["llm"].received_messages


@pytest.mark.asyncio
async def test_question_route_preserves_agent_behavior(
    _patch_tenant_repo: None,
) -> None:
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
async def test_lead_route_returns_lead_response(_patch_tenant_repo: None) -> None:
    deps = _base_deps()
    prediction = _make_prediction("lead", "capture_lead")

    class LeadClassifier:
        async def predict(self, message: str) -> ClassifierPrediction:
            return prediction

    response = await chat(classifier=LeadClassifier(), **deps)  # type: ignore[arg-type]

    assert response.answer == LEAD_MESSAGE
    assert not deps["llm"].received_messages


@pytest.mark.asyncio
async def test_escalate_route_returns_escalate_response(
    _patch_tenant_repo: None,
) -> None:
    deps = _base_deps()
    prediction = _make_prediction("escalate", "escalate")

    class EscalateClassifier:
        async def predict(self, message: str) -> ClassifierPrediction:
            return prediction

    response = await chat(classifier=EscalateClassifier(), **deps)  # type: ignore[arg-type]

    assert response.answer == ESCALATE_MESSAGE
    assert not deps["llm"].received_messages


@pytest.mark.asyncio
async def test_none_classifier_runs_normal_agent(_patch_tenant_repo: None) -> None:
    deps = _base_deps()
    response = await chat(classifier=None, **deps)  # type: ignore[arg-type]

    assert response.answer == "Tenant-safe response."
    assert deps["llm"].received_messages


@pytest.mark.asyncio
async def test_agent_handoff_runs_normal_agent(_patch_tenant_repo: None) -> None:
    deps = _base_deps()
    prediction = _make_prediction("lead", "agent_handoff", confidence=0.30)

    class HandoffClassifier:
        async def predict(self, message: str) -> ClassifierPrediction:
            return prediction

    response = await chat(classifier=HandoffClassifier(), **deps)  # type: ignore[arg-type]

    assert response.answer == "Tenant-safe response."
    assert deps["llm"].received_messages


# ── New behavior: disallowed origin ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_disallowed_origin_raises_403() -> None:
    from fastapi import HTTPException

    deps = _base_deps()
    deps["http_request"] = FakeRequest({"origin": "https://evil.com"})

    class FakeRestrictiveTenant:
        allowed_origins = ["https://my-site.com"]
        guardrail_config = {}

    with patch(
        "app.api.chat.tenant_repo.get_by_id",
        AsyncMock(return_value=FakeRestrictiveTenant()),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await chat(classifier=None, **deps)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Origin not allowed"


# ── New behavior: guardrails input refusal ───────────────────────────────────


@pytest.mark.asyncio
async def test_guardrails_input_refusal_blocks_llm(_patch_tenant_repo: None) -> None:
    deps = _base_deps()

    class RefusingGuardrails:
        async def check_input(
            self,
            tenant_id: object,
            message: str,
            tenant_config: object = None,
        ) -> GuardrailResponse:
            return GuardrailResponse(
                decision="refuse", reason="Blocked for security policy."
            )

        async def check_output(
            self,
            tenant_id: object,
            message: str,
            tenant_config: object = None,
        ) -> GuardrailResponse:
            return GuardrailResponse(decision="allow")

    deps["guardrails"] = RefusingGuardrails()
    response = await chat(classifier=None, **deps)  # type: ignore[arg-type]

    assert response.answer == "Blocked for security policy."
    assert not deps["llm"].received_messages


# ── New behavior: guardrails output safe_text override ───────────────────────


@pytest.mark.asyncio
async def test_guardrails_output_safe_text_replaces_answer(
    _patch_tenant_repo: None,
) -> None:
    deps = _base_deps()

    class SanitizingGuardrails:
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
            return GuardrailResponse(
                decision="allow",
                safe_text="Sanitized: Tenant-safe response.",
            )

    deps["guardrails"] = SanitizingGuardrails()
    response = await chat(classifier=None, **deps)  # type: ignore[arg-type]

    assert response.answer == "Sanitized: Tenant-safe response."


# ── Origin enforcement ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_allowed_origin_succeeds() -> None:
    tenant = type(
        "FakeTenant",
        (),
        {"allowed_origins": ["https://tenant.example.com"], "guardrail_config": {}},
    )()
    deps = _base_deps()
    deps["http_request"] = FakeRequest({"origin": "https://tenant.example.com"})

    with patch(
        "app.api.chat.tenant_repo.get_by_id",
        AsyncMock(return_value=tenant),
    ):
        response = await chat(classifier=None, **deps)  # type: ignore[arg-type]

    assert response.answer == "Tenant-safe response."
    assert response.conversation_id == "conversation-1"


@pytest.mark.asyncio
async def test_missing_origin_rejected_when_allowlist_non_empty() -> None:
    from fastapi import HTTPException

    tenant = type(
        "FakeTenant",
        (),
        {"allowed_origins": ["https://tenant.example.com"], "guardrail_config": {}},
    )()
    deps = _base_deps()
    deps["http_request"] = FakeRequest({})

    with patch(
        "app.api.chat.tenant_repo.get_by_id",
        AsyncMock(return_value=tenant),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await chat(classifier=None, **deps)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_origin_with_path_rejected() -> None:
    """normalize_origin() rejects non-origin URLs such as those with a path."""
    from fastapi import HTTPException

    tenant = type(
        "FakeTenant",
        (),
        {"allowed_origins": ["https://tenant.example.com"], "guardrail_config": {}},
    )()
    deps = _base_deps()
    deps["http_request"] = FakeRequest(
        {"origin": "https://tenant.example.com/some/path"}
    )

    with patch(
        "app.api.chat.tenant_repo.get_by_id",
        AsyncMock(return_value=tenant),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await chat(classifier=None, **deps)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_empty_allowlist_temporary_allow_all() -> None:
    """Empty allowed_origins is a temporary allow-all until per-tenant
    origin configuration is stored and enforced."""
    tenant = type(
        "FakeTenant",
        (),
        {"allowed_origins": [], "guardrail_config": {}},
    )()
    deps = _base_deps()
    deps["http_request"] = FakeRequest({})

    with patch(
        "app.api.chat.tenant_repo.get_by_id",
        AsyncMock(return_value=tenant),
    ):
        response = await chat(classifier=None, **deps)  # type: ignore[arg-type]

    assert response.answer == "Tenant-safe response."


# ── Redaction ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_redacted_message_used_downstream(
    _patch_tenant_repo: None,
) -> None:
    raw = "Contact me at hadi@example.com"
    redacted = "Contact me at [REDACTED_EMAIL]"

    class EmailRedactor:
        def redact(self, text: str) -> str:
            return re.sub(r"[\w\.-]+@[\w\.-]+", "[REDACTED_EMAIL]", text)

    class SpyClassifier:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def predict(self, message: str) -> ClassifierPrediction:
            self.calls.append(message)
            return _make_prediction("question", "rag_search")

    deps = _base_deps()
    deps["request"] = ChatRequest(message=raw, conversation_id="conv-1")
    deps["redactor"] = EmailRedactor()
    guardrails = FakeGuardrails()
    deps["guardrails"] = guardrails
    classifier = SpyClassifier()

    response = await chat(classifier=classifier, **deps)  # type: ignore[arg-type]

    assert response.answer == "Tenant-safe response."
    assert guardrails.input_checks[0][1] == redacted
    assert classifier.calls[0] == redacted
    messages = deps["llm"].received_messages
    assert str(messages[-1].content) == redacted
    key = build_session_key(
        deps["tenant_context"].tenant_id, deps["tenant_context"].session_id
    )
    saved = [json.loads(m) for m in deps["redis"].lists[key]]
    assert saved[0]["content"] == redacted
    for entry in deps["redis"].lists[key]:
        assert "hadi@example.com" not in entry


# ── Guardrails input refusal ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_guardrails_input_refusal_blocks_entire_pipeline(
    _patch_tenant_repo: None,
) -> None:
    class SpyClassifier:
        def __init__(self) -> None:
            self.called = False

        async def predict(self, message: str) -> ClassifierPrediction:
            self.called = True
            return _make_prediction("question", "rag_search")

    class RefusingInputGuardrails:
        def __init__(self) -> None:
            self.input_checks: list[tuple] = []
            self.output_checks: list[tuple] = []

        async def check_input(
            self,
            tenant_id: object,
            message: str,
            tenant_config: object = None,
        ) -> GuardrailResponse:
            self.input_checks.append((tenant_id, message))
            return GuardrailResponse(decision="refuse", reason="Blocked")

        async def check_output(
            self,
            tenant_id: object,
            message: str,
            tenant_config: object = None,
        ) -> GuardrailResponse:
            self.output_checks.append((tenant_id, message))
            return GuardrailResponse(decision="allow")

    deps = _base_deps()
    deps["guardrails"] = RefusingInputGuardrails()
    classifier = SpyClassifier()

    response = await chat(classifier=classifier, **deps)  # type: ignore[arg-type]

    assert response.answer == "Blocked"
    assert not deps["llm"].received_messages
    assert not classifier.called
    assert deps["guardrails"].output_checks == []
    key = build_session_key(
        deps["tenant_context"].tenant_id, deps["tenant_context"].session_id
    )
    assert key not in deps["redis"].lists
    assert deps["redis"].lrange_calls == []


# ── Guardrails output refusal ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_guardrails_output_refusal_replaces_answer_and_memory(
    _patch_tenant_repo: None,
) -> None:
    class RefusingOutputGuardrails:
        def __init__(self) -> None:
            self.input_checks: list[tuple] = []
            self.output_checks: list[tuple] = []

        async def check_input(
            self,
            tenant_id: object,
            message: str,
            tenant_config: object = None,
        ) -> GuardrailResponse:
            self.input_checks.append((tenant_id, message))
            return GuardrailResponse(decision="allow")

        async def check_output(
            self,
            tenant_id: object,
            message: str,
            tenant_config: object = None,
        ) -> GuardrailResponse:
            self.output_checks.append((tenant_id, message))
            return GuardrailResponse(decision="refuse")

    deps = _base_deps()
    deps["guardrails"] = RefusingOutputGuardrails()

    response = await chat(classifier=None, **deps)  # type: ignore[arg-type]

    assert response.answer == "I'm sorry, I'm unable to provide that response."
    assert deps["llm"].received_messages
    key = build_session_key(
        deps["tenant_context"].tenant_id, deps["tenant_context"].session_id
    )
    saved = [json.loads(m) for m in deps["redis"].lists[key]]
    assert saved[1]["content"] == "I'm sorry, I'm unable to provide that response."
    assert "Tenant-safe response." not in saved[1]["content"]


# ── Guardrails input safe_text overrides downstream ────────────────────────


@pytest.mark.asyncio
async def test_guardrails_input_safe_text_used_downstream(
    _patch_tenant_repo: None,
) -> None:
    raw = "Contact me at hadi@example.com for details"
    redacted_partial = "Contact me at hadi@example.com [OK]"
    guardrails_safe = "Contact me at [SAFE] for details"

    class BrokenRedactor:
        def redact(self, text: str) -> str:
            return redacted_partial

    class SpyClassifier:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def predict(self, message: str) -> ClassifierPrediction:
            self.calls.append(message)
            return _make_prediction("question", "rag_search")

    class SanitizingInputGuardrails:
        def __init__(self) -> None:
            self.input_checks: list[tuple] = []
            self.output_checks: list[tuple] = []

        async def check_input(
            self,
            tenant_id: object,
            message: str,
            tenant_config: object = None,
        ) -> GuardrailResponse:
            self.input_checks.append((tenant_id, message))
            return GuardrailResponse(decision="allow", safe_text=guardrails_safe)

        async def check_output(
            self,
            tenant_id: object,
            message: str,
            tenant_config: object = None,
        ) -> GuardrailResponse:
            self.output_checks.append((tenant_id, message))
            return GuardrailResponse(decision="allow")

    deps = _base_deps()
    deps["request"] = ChatRequest(message=raw, conversation_id="conv-1")
    deps["redactor"] = BrokenRedactor()
    deps["guardrails"] = SanitizingInputGuardrails()
    classifier = SpyClassifier()

    response = await chat(classifier=classifier, **deps)  # type: ignore[arg-type]

    assert response.answer == "Tenant-safe response."
    assert classifier.calls[0] == guardrails_safe
    messages = deps["llm"].received_messages
    assert str(messages[-1].content) == guardrails_safe
    key = build_session_key(
        deps["tenant_context"].tenant_id, deps["tenant_context"].session_id
    )
    saved = [json.loads(m) for m in deps["redis"].lists[key]]
    assert saved[0]["content"] == guardrails_safe
    assert "hadi@example.com" not in saved[0]["content"]
    for entry in deps["redis"].lists[key]:
        assert "hadi@example.com" not in entry
