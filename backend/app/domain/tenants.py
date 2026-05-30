"""Tenant provisioning and configuration types."""

from datetime import date
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class TenantDetail(TenantResponse):
    llm_persona: str
    guardrail_config: dict[str, Any]
    allowed_origins: list[str]


class TenantConfigUpdate(BaseModel):
    llm_persona: str | None = None
    guardrail_config: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class TenantCostResponse(BaseModel):
    tenant_id: UUID
    start_day: date
    end_day: date
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class TenantUserResponse(BaseModel):
    id: UUID
    email: str
    role: str
    tenant_id: UUID | None
    is_active: bool
    created_at: str

    model_config = ConfigDict(from_attributes=True)
