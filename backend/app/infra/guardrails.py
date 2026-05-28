"""Async client for the NeMo Guardrails sidecar."""

from typing import Any, Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.core.config import Settings

GuardrailDecision = Literal["allow", "refuse"]


class GuardrailRequest(BaseModel):
    """Request sent from backend to the guardrails sidecar."""

    tenant_id: UUID
    message: str = Field(..., min_length=1, max_length=4000)
    tenant_config: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class GuardrailResponse(BaseModel):
    """Guardrail sidecar decision."""

    decision: GuardrailDecision
    reason: str | None = None
    safe_text: str | None = None
    triggered_rules: list[str] = Field(default_factory=list)


class GuardrailsClient:
    """HTTP client for input and output guardrail checks."""

    def __init__(self, http_client: httpx.AsyncClient, settings: Settings) -> None:
        self._http_client = http_client
        self._base_url = settings.guardrails_url.rstrip("/")
        self._token = settings.guardrails_token.get_secret_value()

    def _headers(self) -> dict[str, str]:
        """Build service-token auth headers."""
        if not self._token:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    async def check_input(
        self,
        tenant_id: UUID,
        message: str,
        tenant_config: dict[str, Any] | None = None,
    ) -> GuardrailResponse:
        """Check visitor input before router or agent execution."""
        payload = GuardrailRequest(
            tenant_id=tenant_id,
            message=message,
            tenant_config=tenant_config or {},
        )

        response = await self._http_client.post(
            f"{self._base_url}/check_input",
            headers=self._headers(),
            json=payload.model_dump(mode="json"),
            timeout=10.0,
        )
        response.raise_for_status()
        return GuardrailResponse.model_validate(response.json())

    async def check_output(
        self,
        tenant_id: UUID,
        message: str,
        tenant_config: dict[str, Any] | None = None,
    ) -> GuardrailResponse:
        """Check assistant output before returning it to the visitor."""
        payload = GuardrailRequest(
            tenant_id=tenant_id,
            message=message,
            tenant_config=tenant_config or {},
        )

        response = await self._http_client.post(
            f"{self._base_url}/check_output",
            headers=self._headers(),
            json=payload.model_dump(mode="json"),
            timeout=10.0,
        )
        response.raise_for_status()
        return GuardrailResponse.model_validate(response.json())

    async def healthz(self) -> bool:
        """Check guardrails sidecar health."""
        response = await self._http_client.get(
            f"{self._base_url}/healthz",
            timeout=3.0,
        )
        return response.status_code == 200
