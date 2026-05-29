"""Unit tests for PII redaction. Requires en_core_web_sm to be installed."""

import pytest

from app.security.redaction import Redactor


@pytest.fixture(scope="module")
def redactor() -> Redactor:
    return Redactor()


def test_plain_text_returned_unchanged(redactor: Redactor) -> None:
    text = "What are your business hours on weekends?"
    assert redactor.redact(text) == text


def test_redacts_email_address(redactor: Redactor) -> None:
    text = "Please email me at john.doe@example.com for more information."
    redacted = redactor.redact(text)

    assert "john.doe@example.com" not in redacted
    assert "REDACTED" in redacted


def test_redacts_phone_number(redactor: Redactor) -> None:
    text = "You can reach me at 555-867-5309 anytime."
    redacted = redactor.redact(text)

    assert "555-867-5309" not in redacted
    assert "REDACTED" in redacted


def test_multiple_pii_entities_all_replaced(redactor: Redactor) -> None:
    text = "Contact Alice at alice@corp.com or call 555-867-5309."
    redacted = redactor.redact(text)

    assert "alice@corp.com" not in redacted
    assert "555-867-5309" not in redacted


def test_redacted_tokens_use_entity_type_label(redactor: Redactor) -> None:
    text = "Email: test@example.org"
    redacted = redactor.redact(text)

    assert "test@example.org" not in redacted
    assert "[REDACTED_" in redacted
