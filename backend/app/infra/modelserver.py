"""Async client for the Concierge classifier model-server."""

from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.core.config import Settings

IntentLabel = Literal["spam", "question", "lead", "escalate"]
RouteHint = Literal[
    "drop",
    "rag_search",
    "capture_lead",
    "escalate",
    "agent_handoff",
]


class ClassifierPrediction(BaseModel):
    """Classifier output returned by the model-server."""

    label: IntentLabel
    confidence: float = Field(..., ge=0.0, le=1.0)
    scores: dict[str, float]
    model_version: str
    route_hint: RouteHint


class ModelServerClient:
    """HTTP client for classifier predictions."""

    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http_client = http_client
        self._base_url = settings.model_server_url.rstrip("/")
        self._token = settings.model_server_token.get_secret_value()

    def _headers(self) -> dict[str, str]:
        """Build auth headers for service-to-service calls."""
        if not self._token:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    async def predict(self, text: str) -> ClassifierPrediction:
        """Classify one visitor message."""
        response = await self._http_client.post(
            f"{self._base_url}/predict",
            headers=self._headers(),
            json={"text": text},
            timeout=5.0,
        )
        response.raise_for_status()
        return ClassifierPrediction.model_validate(response.json())

    async def healthz(self) -> bool:
        """Check model-server health."""
        response = await self._http_client.get(
            f"{self._base_url}/healthz",
            timeout=3.0,
        )
        return response.status_code == 200
