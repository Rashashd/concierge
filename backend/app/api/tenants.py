"""Tenant provisioning endpoints — require tenant_manager role."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_session, require_tenant_manager
from app.repositories import tenants as tenant_repo
from app.schemas import TenantCreate, TenantResponse, UserContext

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    _: Annotated[UserContext, Depends(require_tenant_manager)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantResponse:
    async with session.begin():
        existing = await tenant_repo.get_by_slug(session, body.slug)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Slug already in use",
            )
        tenant = await tenant_repo.create(session, name=body.name, slug=body.slug)
    return TenantResponse.model_validate(tenant)


@router.get("/", response_model=list[TenantResponse])
async def list_tenants(
    _: Annotated[UserContext, Depends(require_tenant_manager)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TenantResponse]:
    tenants = await tenant_repo.list_all(session)
    return [TenantResponse.model_validate(t) for t in tenants]


@router.post("/{tenant_id}/suspend", response_model=TenantResponse)
async def suspend_tenant(
    tenant_id: uuid.UUID,
    _: Annotated[UserContext, Depends(require_tenant_manager)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantResponse:
    async with session.begin():
        tenant = await tenant_repo.suspend(session, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return TenantResponse.model_validate(tenant)
