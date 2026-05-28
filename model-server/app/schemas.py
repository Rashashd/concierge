"""Pydantic contracts for the classifier model-server API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

IntentLabel = Literal["spam", "question", "lead", "escalate"]
RouteHint = Literal[
    "drop",
    "rag_search",
    "capture_lead",
    "escalate",
    "agent_handoff",
]


class PredictRequest(BaseModel):
    """Request body for one classifier prediction."""

    text: str = Field(..., min_length=1, max_length=4000)

    model_config = ConfigDict(extra="forbid")


class PredictResponse(BaseModel):
    """Classifier prediction returned to the backend router."""

    label: IntentLabel
    confidence: float = Field(..., ge=0.0, le=1.0)
    scores: dict[str, float]
    model_version: str
    route_hint: RouteHint


class MetadataResponse(BaseModel):
    """Metadata about the loaded classifier artifact."""

    model_version: str
    shipped_model: str
    confidence_threshold: float
    labels: list[str]
    serving_method: str | None = None
