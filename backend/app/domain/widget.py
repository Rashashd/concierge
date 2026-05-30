"""Widget token and config types."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WidgetTokenRequest(BaseModel):
    widget_id: UUID
    session_id: str = Field(..., min_length=1, max_length=255)

    model_config = ConfigDict(extra="forbid")


class WidgetTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class WidgetConfigPublic(BaseModel):
    widget_id: UUID
    greeting: str
    theme_color: str


class WidgetConfigCreate(BaseModel):
    greeting: str = "Hi, how can I help you?"
    theme_color: str = "#0066CC"
    enabled_tools: list[str] = ["rag_search", "capture_lead", "escalate"]
