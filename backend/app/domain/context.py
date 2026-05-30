"""Request-context types from verified tokens, never from user input."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TenantContext(BaseModel):
    tenant_id: UUID
    widget_id: UUID
    session_id: str = Field(..., min_length=1, max_length=255)


class UserContext(BaseModel):
    user_id: UUID
    role: Literal["tenant_manager", "tenant_admin"]
    tenant_id: UUID | None  # None for tenant_manager
