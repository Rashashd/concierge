"""Content item types."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

ContentType = Literal["faq", "page", "blog"]


class ContentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    body: str = Field(..., min_length=1)
    content_type: ContentType = Field(default="faq")

    model_config = ConfigDict(extra="forbid")


class ContentUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=500)
    body: str | None = None
    content_type: ContentType | None = None

    model_config = ConfigDict(extra="forbid")


class ContentResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    title: str
    body: str
    content_type: str
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)
