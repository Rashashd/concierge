"""Async client for the Concierge classifier model-server."""

import httpx

from app.core.config import Settings
from app.services.classifier_router import ClassifierPrediction, ClassifierScores


class ModelServerClient:
    """HTTP client for classifier predictions."""

    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http_client = http_client
        self._base_url = settings.model_server_url.rstrip("/")
        self._token = settings.model_server_token.get_secret_value()

    def _headers(self) -> dict[str, str]:
        if not self._token:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    async def predict(self, message: str) -> ClassifierPrediction:
        """Classify one visitor message."""
        response = await self._http_client.post(
            f"{self._base_url}/predict",
            headers=self._headers(),
            json={"text": message},
            timeout=5.0,
        )
        response.raise_for_status()
        data = response.json()
        raw_scores = data.get("scores", {})
        data["scores"] = ClassifierScores(
            spam=float(raw_scores.get("spam", 0.0)),
            question=float(raw_scores.get("question", 0.0)),
            lead=float(raw_scores.get("lead", 0.0)),
            escalate=float(raw_scores.get("escalate", 0.0)),
        )
        return ClassifierPrediction.model_validate(data)

    async def healthz(self) -> bool:
        """Check model-server health."""
        response = await self._http_client.get(
            f"{self._base_url}/healthz",
            timeout=3.0,
        )
        return response.status_code == 200
