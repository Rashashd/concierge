"""Agent tool contracts — input/output schemas and shared error type."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ToolError(BaseModel):
    tool: str
    code: str
    message: str


class RAGSearchInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)

    model_config = ConfigDict(extra="forbid")


class ChunkReference(BaseModel):
    chunk_id: UUID
    content_item_id: UUID
    text: str
    score: float


class RAGSearchOutput(BaseModel):
    answer: str
    source_chunks: list[ChunkReference]


class ChatRouteStatus(BaseModel):
    route: Literal["agent"] = "agent"


class CaptureLeadInput(BaseModel):
    visitor_name: str | None = Field(default=None, max_length=255)
    contact: str = Field(..., max_length=320)
    intent: str = Field(..., min_length=1, max_length=1000)
    session_id: str = Field(..., max_length=255)

    model_config = ConfigDict(extra="forbid")


class CaptureLeadOutput(BaseModel):
    lead_id: UUID
    status: Literal["captured", "duplicate"]


class EscalateInput(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)
    conversation_id: str = Field(..., max_length=255)

    model_config = ConfigDict(extra="forbid")


class EscalateOutput(BaseModel):
    ticket_id: UUID
    status: Literal["escalated"]
    visitor_message: str
