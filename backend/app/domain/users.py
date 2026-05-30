"""User schemas for fastapi-users integration."""

from typing import Literal
from uuid import UUID

from fastapi_users import schemas as fu_schemas


class UserRead(fu_schemas.BaseUser[UUID]):
    role: str
    tenant_id: UUID | None


class UserCreate(fu_schemas.BaseUserCreate):
    role: Literal["tenant_manager", "tenant_admin"] = "tenant_admin"
    tenant_id: UUID | None = None


class UserUpdate(fu_schemas.BaseUserUpdate):
    role: Literal["tenant_manager", "tenant_admin"] | None = None
    tenant_id: UUID | None = None
