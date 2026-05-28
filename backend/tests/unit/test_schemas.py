from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import (
    CaptureLeadInput,
    ChatRequest,
    EscalateInput,
    RAGSearchInput,
    TenantCreate,
)

# ChatRequest


def test_chat_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"message": "hi", "tenant_id": str(uuid4())})


def test_chat_request_rejects_empty_message() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"message": ""})


def test_chat_request_rejects_whitespace_only_message() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"message": "   "})


def test_chat_request_rejects_message_over_4000_chars() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"message": "x" * 4001})


def test_chat_request_conversation_id_defaults_to_none() -> None:
    req = ChatRequest.model_validate({"message": "hello"})
    assert req.conversation_id is None


def test_chat_request_accepts_optional_conversation_id() -> None:
    req = ChatRequest.model_validate({"message": "hello", "conversation_id": "abc"})
    assert req.conversation_id == "abc"


# RAGSearchInput


def test_rag_search_input_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        RAGSearchInput.model_validate({"query": ""})


def test_rag_search_input_rejects_query_over_1000_chars() -> None:
    with pytest.raises(ValidationError):
        RAGSearchInput.model_validate({"query": "q" * 1001})


def test_rag_search_input_rejects_top_k_below_1() -> None:
    with pytest.raises(ValidationError):
        RAGSearchInput.model_validate({"query": "q", "top_k": 0})


def test_rag_search_input_rejects_top_k_above_20() -> None:
    with pytest.raises(ValidationError):
        RAGSearchInput.model_validate({"query": "q", "top_k": 21})


def test_rag_search_input_default_top_k_is_5() -> None:
    req = RAGSearchInput.model_validate({"query": "q"})
    assert req.top_k == 5


def test_rag_search_input_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        RAGSearchInput.model_validate({"query": "q", "tenant_id": str(uuid4())})


# TenantCreate


def test_tenant_create_accepts_valid_slug() -> None:
    t = TenantCreate.model_validate({"name": "Acme Corp", "slug": "acme-corp"})
    assert t.slug == "acme-corp"


@pytest.mark.parametrize(
    "bad_slug",
    [
        "Acme",         # uppercase
        "acme corp",    # space
        "acme_corp",    # underscore
        "acme!",        # special char
        "",             # empty
    ],
)
def test_tenant_create_rejects_invalid_slug(bad_slug: str) -> None:
    with pytest.raises(ValidationError):
        TenantCreate.model_validate({"name": "Test", "slug": bad_slug})


def test_tenant_create_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        TenantCreate.model_validate({"name": "T", "slug": "t", "id": str(uuid4())})


# CaptureLeadInput


def test_capture_lead_input_requires_contact_and_intent() -> None:
    with pytest.raises(ValidationError):
        CaptureLeadInput.model_validate({"session_id": "s1"})


def test_capture_lead_input_allows_null_visitor_name() -> None:
    lead = CaptureLeadInput.model_validate(
        {"contact": "user@example.com", "intent": "buy product", "session_id": "s1"}
    )
    assert lead.visitor_name is None


def test_capture_lead_input_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CaptureLeadInput.model_validate(
            {
                "contact": "a@b.com",
                "intent": "buy",
                "session_id": "s1",
                "tenant_id": str(uuid4()),
            }
        )


# EscalateInput


def test_escalate_input_rejects_empty_reason() -> None:
    with pytest.raises(ValidationError):
        EscalateInput.model_validate({"reason": "", "conversation_id": "c1"})


def test_escalate_input_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EscalateInput.model_validate(
            {"reason": "need help", "conversation_id": "c1", "tenant_id": str(uuid4())}
        )
