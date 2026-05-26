from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TenantContext(BaseModel):
    tenant_id: UUID
    widget_id: UUID
    session_id: str = Field(..., min_length=1, max_length=255)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=255)

    model_config = ConfigDict(extra="forbid")


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str | None = None


class WidgetTokenRequest(BaseModel):
    widget_id: UUID
    session_id: str = Field(..., min_length=1, max_length=255)

    model_config = ConfigDict(extra="forbid")


class WidgetTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


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
