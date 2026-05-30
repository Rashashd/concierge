"""Lead capture and status types."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

LeadStatus = Literal["new", "contacted", "closed", "qualified"]


class LeadResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    session_id: str
    visitor_name: str | None
    contact: str
    intent: str
    status: str
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class LeadStatusUpdate(BaseModel):
    status: LeadStatus

    model_config = ConfigDict(extra="forbid")
