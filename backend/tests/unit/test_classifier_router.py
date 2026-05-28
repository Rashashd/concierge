import pytest
from pydantic import ValidationError

from app.services.classifier_router import (
    ClassifierPrediction,
    ClassifierScores,
    ConversationRoute,
    route_conversation,
)


def _make_prediction(
    label: str,
    route_hint: str,
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


def test_none_prediction_returns_agent():
    result = route_conversation(None)
    assert result.action == "agent"
    assert result.reason == "classifier_unavailable"
    assert result.prediction is None


def test_agent_handoff_route_hint_returns_agent():
    prediction = _make_prediction("spam", "agent_handoff", confidence=0.45)
    result = route_conversation(prediction)
    assert result.action == "agent"
    assert result.reason == "low_confidence"
    assert result.prediction is prediction


def test_low_confidence_spam_still_returns_agent():
    prediction = _make_prediction("question", "agent_handoff", confidence=0.30)
    result = route_conversation(prediction)
    assert result.action == "agent"
    assert result.reason == "low_confidence"


def test_spam_label_returns_refuse():
    prediction = _make_prediction("spam", "drop", confidence=0.99)
    result = route_conversation(prediction)
    assert result.action == "refuse"
    assert result.reason == "spam"
    assert result.prediction is prediction


def test_drop_route_hint_returns_refuse():
    prediction = _make_prediction("spam", "drop", confidence=0.88)
    result = route_conversation(prediction)
    assert result.action == "refuse"
    assert result.reason == "spam"


def test_question_label_returns_agent():
    prediction = _make_prediction("question", "rag_search", confidence=0.92)
    result = route_conversation(prediction)
    assert result.action == "agent"
    assert result.reason == "question"
    assert result.prediction is prediction


def test_rag_search_route_hint_returns_agent():
    prediction = _make_prediction("question", "rag_search", confidence=0.85)
    result = route_conversation(prediction)
    assert result.action == "agent"
    assert result.reason == "question"


def test_lead_label_returns_lead():
    prediction = _make_prediction("lead", "capture_lead", confidence=0.90)
    result = route_conversation(prediction)
    assert result.action == "lead"
    assert result.reason == "lead"
    assert result.prediction is prediction


def test_capture_lead_route_hint_returns_lead():
    prediction = _make_prediction("lead", "capture_lead", confidence=0.78)
    result = route_conversation(prediction)
    assert result.action == "lead"
    assert result.reason == "lead"


def test_escalate_label_returns_escalate():
    prediction = _make_prediction("escalate", "escalate", confidence=0.96)
    result = route_conversation(prediction)
    assert result.action == "escalate"
    assert result.reason == "escalate"
    assert result.prediction is prediction


def test_escalate_route_hint_returns_escalate():
    prediction = _make_prediction("escalate", "escalate", confidence=0.81)
    result = route_conversation(prediction)
    assert result.action == "escalate"
    assert result.reason == "escalate"


def test_fallback_to_agent_when_label_does_not_match():
    prediction = ClassifierPrediction(
        label="spam",
        confidence=0.99,
        scores=ClassifierScores(spam=0.99),
        model_version="1.0.0",
        route_hint="drop",
    )
    result = route_conversation(prediction)
    assert result.action == "refuse"


def test_route_conversation_preserves_model_version():
    prediction = _make_prediction("question", "rag_search")
    prediction.model_version = "3.2.1"
    result = route_conversation(prediction)
    assert result.prediction is not None
    assert result.prediction.model_version == "3.2.1"


def test_classifier_scores_extra_forbidden():
    with pytest.raises(ValidationError):
        ClassifierScores.model_validate(
            {"spam": 0.1, "question": 0.8, "lead": 0.05, "escalate": 0.05, "bonus": 0.0}
        )


def test_conversation_route_defaults():
    route = ConversationRoute(action="agent", reason="test")
    assert route.prediction is None


def test_classifier_prediction_extra_forbidden():
    with pytest.raises(ValidationError):
        ClassifierPrediction.model_validate(
            {
                "label": "spam",
                "confidence": 0.99,
                "scores": {"spam": 0.99, "question": 0.0, "lead": 0.0, "escalate": 0.0},
                "model_version": "1.0.0",
                "route_hint": "drop",
                "tenant_id": "abc",
            }
        )
