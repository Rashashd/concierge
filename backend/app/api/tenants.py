"""Tenant provisioning endpoints — require tenant_manager role."""

import uuid
from datetime import date, datetime, timezone
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.dependencies import get_redis, get_session, require_tenant_manager
from app.infra.minio import MinioClient
from app.repositories import cost_records as cost_repo
from app.repositories import tenants as tenant_repo
from app.schemas import TenantCostResponse, TenantCreate, TenantResponse, UserContext
from app.services.erasure import ErasureReport, erase_tenant

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


@router.get("/{tenant_id}/cost", response_model=TenantCostResponse)
async def get_tenant_cost(
    tenant_id: uuid.UUID,
    _: Annotated[UserContext, Depends(require_tenant_manager)],
    session: Annotated[AsyncSession, Depends(get_session)],
    day: Annotated[date | None, Query(description="UTC calendar day (YYYY-MM-DD). Defaults to today.")] = None,
) -> TenantCostResponse:
    if day is None:
        day = datetime.now(timezone.utc).date()
    totals = await cost_repo.get_daily_totals(session, tenant_id, day)
    return TenantCostResponse(tenant_id=tenant_id, day=day, **totals)


@router.post("/{tenant_id}/erase", response_model=ErasureReport)
async def erase_tenant_data(
    tenant_id: uuid.UUID,
    user: Annotated[UserContext, Depends(require_tenant_manager)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ErasureReport:
    async with session.begin():
        tenant = await tenant_repo.get_by_id(session, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return await erase_tenant(
        tenant_id=tenant_id,
        actor_id=user.user_id,
        actor_role=user.role,
        session=session,
        redis=redis,
        minio=MinioClient(settings),
    )
