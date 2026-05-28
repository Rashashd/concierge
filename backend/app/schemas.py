from datetime import date
from typing import Literal
from uuid import UUID

from fastapi_users import schemas as fu_schemas
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TenantContext(BaseModel):
    tenant_id: UUID
    widget_id: UUID
    session_id: str = Field(..., min_length=1, max_length=255)


class UserContext(BaseModel):
    user_id: UUID
    role: Literal["tenant_manager", "tenant_admin"]
    tenant_id: UUID | None  # None for tenant_manager


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=255)

    model_config = ConfigDict(extra="forbid")

    @field_validator("message")
    @classmethod
    def message_must_not_be_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be empty or whitespace-only")
        return v


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


# Tool contracts

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


# Tenant provisioning

class TenantCostResponse(BaseModel):
    tenant_id: UUID
    day: date
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")

    model_config = ConfigDict(extra="forbid")


class TenantResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


# User schemas for fastapi-users

class UserRead(fu_schemas.BaseUser[UUID]):
    role: str
    tenant_id: UUID | None


class UserCreate(fu_schemas.BaseUserCreate):
    role: Literal["tenant_manager", "tenant_admin"] = "tenant_admin"
    tenant_id: UUID | None = None


class UserUpdate(fu_schemas.BaseUserUpdate):
    role: Literal["tenant_manager", "tenant_admin"] | None = None
    tenant_id: UUID | None = None
