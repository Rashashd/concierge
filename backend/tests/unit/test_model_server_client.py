"""Unit tests for infra/model_server.py — HTTP client and response parsing."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infra.model_server import ModelServerClient
from app.services.classifier_router import ClassifierScores


def _make_settings(
    token: str = "secret-token", url: str = "http://model:8001"
) -> MagicMock:
    s = MagicMock()
    s.model_server_url = url
    s.model_server_token.get_secret_value.return_value = token
    return s


def _make_response(label: str = "question", confidence: float = 0.9) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    base_scores = {"spam": 0.01, "question": 0.01, "lead": 0.01, "escalate": 0.01}
    base_scores[label] = confidence
    resp.json.return_value = {
        "label": label,
        "confidence": confidence,
        "route_hint": "rag_search",
        "model_version": "v1",
        "scores": base_scores,
    }
    return resp


@pytest.mark.asyncio
async def test_predict_sends_bearer_token_header() -> None:
    http = AsyncMock()
    http.post.return_value = _make_response()
    client = ModelServerClient(http, _make_settings(token="my-token"))

    await client.predict("What are your hours?")

    headers = http.post.call_args.kwargs["headers"]
    assert headers.get("Authorization") == "Bearer my-token"


@pytest.mark.asyncio
async def test_predict_sends_no_auth_header_when_token_is_empty() -> None:
    http = AsyncMock()
    http.post.return_value = _make_response()
    client = ModelServerClient(http, _make_settings(token=""))

    await client.predict("hi")

    headers = http.post.call_args.kwargs["headers"]
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_predict_parses_scores_into_classifier_scores() -> None:
    http = AsyncMock()
    http.post.return_value = _make_response(label="lead", confidence=0.85)
    client = ModelServerClient(http, _make_settings())

    result = await client.predict("I want to sign up.")

    assert result.label == "lead"
    assert result.confidence == pytest.approx(0.85)
    assert isinstance(result.scores, ClassifierScores)
    assert result.scores.lead == pytest.approx(0.85)


@pytest.mark.asyncio
async def test_predict_posts_to_correct_url() -> None:
    http = AsyncMock()
    http.post.return_value = _make_response()
    client = ModelServerClient(http, _make_settings(url="http://model:8001"))

    await client.predict("hello")

    url = http.post.call_args.args[0]
    assert url == "http://model:8001/predict"


@pytest.mark.asyncio
async def test_healthz_returns_true_on_200() -> None:
    resp = MagicMock()
    resp.status_code = 200
    http = AsyncMock()
    http.get.return_value = resp
    client = ModelServerClient(http, _make_settings())

    result = await client.healthz()

    assert result is True


@pytest.mark.asyncio
async def test_healthz_returns_false_on_non_200() -> None:
    resp = MagicMock()
    resp.status_code = 503
    http = AsyncMock()
    http.get.return_value = resp
    client = ModelServerClient(http, _make_settings())

    result = await client.healthz()

    assert result is False
