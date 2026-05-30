"""Audit log and escalation response types."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    id: UUID
    actor_id: UUID
    actor_email: str | None
    actor_role: str
    tenant_id: UUID | None
    action: str
    payload: dict[str, Any]
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class EscalationResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    conversation_id: str
    reason: str
    created_at: str
