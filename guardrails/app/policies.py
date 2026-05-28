"""Deterministic defense-in-depth policies for the NeMo sidecar."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

Decision = Literal["allow", "refuse"]


INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bignore\b.*\b(previous|prior|system|developer)\b.*\binstructions?\b",
        re.I,
    ),
    re.compile(
        r"\b(reveal|show|print|display|dump|expose)\b.*\b("
        r"system prompt|developer message|developer prompt|hidden prompt|"
        r"hidden instructions|internal policy|internal instructions"
        r")\b",
        re.I,
    ),
    re.compile(
        r"\b(system prompt|developer message|developer prompt|hidden prompt|"
        r"hidden instructions|internal policy|internal instructions)\b",
        re.I,
    ),
    re.compile(r"\bjailbreak\b", re.I),
    re.compile(r"\bdan mode\b", re.I),
    re.compile(r"\bdeveloper mode\b", re.I),
    re.compile(r"\bact as\b.*\bwithout restrictions\b", re.I),
    re.compile(r"\banswer\b.*\bwithout\b.*\b(safety|rules|restrictions)\b", re.I),
)

CROSS_TENANT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\btenant\s+[b-z]\b", re.I),
    re.compile(r"\banother tenant\b", re.I),
    re.compile(r"\bother tenant", re.I),
    re.compile(r"\bcross[-\s]?tenant\b", re.I),
    re.compile(r"\ball tenants\b", re.I),
    re.compile(r"\banother customer", re.I),
    re.compile(r"\bcompetitor\b.*\b(leads|customers|messages|content)\b", re.I),
)

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"gsk_[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-\.]{12,}"),
)

EMAIL_PATTERN = re.compile(r"[\w.\-+]+@[\w.\-]+\.[A-Za-z]{2,}")
PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")


@dataclass(frozen=True)
class GuardrailResult:
    """Result returned by deterministic policy checks."""

    decision: Decision
    reason: str | None = None
    safe_text: str | None = None
    triggered_rules: list[str] = field(default_factory=list)


def redact_pii(text: str) -> str:
    """Redact common secrets and PII-like strings."""
    safe = text

    for pattern in SECRET_PATTERNS:
        safe = pattern.sub("[REDACTED_SECRET]", safe)

    safe = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", safe)
    safe = PHONE_PATTERN.sub("[REDACTED_PHONE]", safe)

    return safe


def _blocked_topic_match(text: str, blocked_topics: list[str]) -> str | None:
    """Return the first blocked topic found in text."""
    lowered = text.lower()

    for topic in blocked_topics:
        clean_topic = str(topic).strip().lower()
        if clean_topic and clean_topic in lowered:
            return clean_topic

    return None


def check_input_policy(
    message: str,
    tenant_config: dict[str, Any] | None = None,
) -> GuardrailResult:
    """Apply deterministic input checks before or after NeMo."""
    tenant_config = tenant_config or {}

    for pattern in INJECTION_PATTERNS:
        if pattern.search(message):
            return GuardrailResult(
                decision="refuse",
                reason="Prompt-injection or jailbreak attempt refused.",
                safe_text=None,
                triggered_rules=["platform.prompt_injection"],
            )

    for pattern in CROSS_TENANT_PATTERNS:
        if pattern.search(message):
            return GuardrailResult(
                decision="refuse",
                reason="Cross-tenant data access is not allowed.",
                safe_text=None,
                triggered_rules=["platform.cross_tenant"],
            )

    blocked_topics = tenant_config.get("blocked_topics", [])
    if isinstance(blocked_topics, list):
        match = _blocked_topic_match(message, blocked_topics)
        if match:
            return GuardrailResult(
                decision="refuse",
                reason=f"This tenant blocks the topic: {match}.",
                safe_text=None,
                triggered_rules=["tenant.blocked_topic"],
            )

    return GuardrailResult(
        decision="allow",
        reason=None,
        safe_text=redact_pii(message),
        triggered_rules=[],
    )


def check_output_policy(
    message: str,
    tenant_config: dict[str, Any] | None = None,
) -> GuardrailResult:
    """Apply deterministic output checks and redaction."""
    tenant_config = tenant_config or {}

    for pattern in CROSS_TENANT_PATTERNS:
        if pattern.search(message):
            return GuardrailResult(
                decision="refuse",
                reason="Output appears to expose cross-tenant data.",
                safe_text=None,
                triggered_rules=["platform.cross_tenant_output"],
            )

    safe_text = redact_pii(message)

    refusal_tone = str(tenant_config.get("refusal_tone", "")).strip()
    if refusal_tone and "cannot" in safe_text.lower():
        safe_text = f"{refusal_tone}: {safe_text}"

    return GuardrailResult(
        decision="allow",
        reason=None,
        safe_text=safe_text,
        triggered_rules=[],
    )
