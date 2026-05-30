"""Tenant provisioning endpoints — require tenant_manager role."""

import uuid
from typing import Annotated, cast

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_minio,
    get_redis,
    get_session,
    require_tenant_admin,
    require_tenant_manager,
)
from app.infra.minio import MinioClient
from app.repositories import audit_log as audit_repo
from app.repositories import tenants as tenant_repo
from app.repositories import users as user_repo
from app.schemas import (
    TenantConfigUpdate,
    TenantCreate,
    TenantDetail,
    TenantResponse,
    TenantUserResponse,
    UserContext,
)
from app.services import tenants as tenant_service
from app.services.erasure import ErasureReport, erase_tenant
from app.services.memory import RedisMemoryClient

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    user: Annotated[UserContext, Depends(require_tenant_manager)],
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
        await audit_repo.create(
            session,
            actor_id=user.user_id,
            actor_role=user.role,
            tenant_id=tenant.id,
            action="tenant.created",
            payload={"name": body.name, "slug": body.slug},
        )
    return TenantResponse.model_validate(tenant)


@router.get("/", response_model=list[TenantResponse])
async def list_tenants(
    _: Annotated[UserContext, Depends(require_tenant_manager)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TenantResponse]:
    tenants = await tenant_repo.list_all(session)
    return [TenantResponse.model_validate(t) for t in tenants]


@router.get("/me", response_model=TenantDetail)
async def get_my_tenant(
    user: Annotated[UserContext, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantDetail:
    if user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenant associated with this account",
        )
    tenant = await tenant_repo.get_by_id(session, user.tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return TenantDetail.model_validate(tenant)


@router.patch("/me/config", response_model=TenantDetail)
async def update_my_tenant_config(
    body: TenantConfigUpdate,
    user: Annotated[UserContext, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantDetail:
    if user.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenant associated with this account",
        )
    async with session.begin():
        tenant = await tenant_repo.update_config(
            session,
            user.tenant_id,
            llm_persona=body.llm_persona,
            guardrail_config=body.guardrail_config,
        )
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return TenantDetail.model_validate(tenant)


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
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return TenantResponse.model_validate(tenant)


@router.post("/{tenant_id}/unsuspend", response_model=TenantResponse)
async def unsuspend_tenant(
    tenant_id: uuid.UUID,
    _: Annotated[UserContext, Depends(require_tenant_manager)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantResponse:
    async with session.begin():
        tenant = await tenant_repo.unsuspend(session, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return TenantResponse.model_validate(tenant)


@router.get("/{tenant_id}/users", response_model=list[TenantUserResponse])
async def list_tenant_users(
    tenant_id: uuid.UUID,
    _: Annotated[UserContext, Depends(require_tenant_manager)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TenantUserResponse]:
    users = await user_repo.list_by_tenant(session, tenant_id=tenant_id)
    return [
        TenantUserResponse(
            id=u.id,
            email=u.email,
            role=u.role,
            tenant_id=u.tenant_id,
            is_active=u.is_active,
            created_at=u.created_at.isoformat(),
        )
        for u in users
    ]


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: uuid.UUID,
    user: Annotated[UserContext, Depends(require_tenant_manager)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
    minio: Annotated[MinioClient, Depends(get_minio)],
) -> None:
    async with session.begin():
        tenant = await tenant_repo.get_by_id(session, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    await tenant_service.full_delete_tenant(
        tenant_id=tenant_id,
        actor_id=user.user_id,
        actor_role=user.role,
        session=session,
        redis=cast(RedisMemoryClient, redis),
        minio=minio,
    )


@router.post("/{tenant_id}/erase", response_model=ErasureReport)
async def erase_tenant_data(
    tenant_id: uuid.UUID,
    user: Annotated[UserContext, Depends(require_tenant_manager)],
    session: Annotated[AsyncSession, Depends(get_session)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
    minio: Annotated[MinioClient, Depends(get_minio)],
) -> ErasureReport:
    async with session.begin():
        tenant = await tenant_repo.get_by_id(session, tenant_id)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return await erase_tenant(
        tenant_id=tenant_id,
        actor_id=user.user_id,
        actor_role=user.role,
        session=session,
        redis=cast(RedisMemoryClient, redis),
        minio=minio,
    )
