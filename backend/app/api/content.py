from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_admin_tenant_session,
    require_tenant_admin,
)
from app.repositories import content as content_repo
from app.schemas import ContentCreate, ContentResponse, ContentUpdate, UserContext

router = APIRouter(prefix="/content", tags=["content"])


@router.post("", response_model=ContentResponse, status_code=status.HTTP_201_CREATED)
async def create_content(
    body: ContentCreate,
    user: Annotated[UserContext, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_admin_tenant_session)],
) -> ContentResponse:
    item = await content_repo.create(
        session=session,
        tenant_id=user.tenant_id,  # type: ignore[arg-type]
        title=body.title,
        body=body.body,
        content_type=body.content_type,
    )
    return ContentResponse(
        id=item.id,
        tenant_id=item.tenant_id,
        title=item.title,
        body=item.body,
        content_type=item.content_type,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


@router.get("", response_model=list[ContentResponse])
async def list_content(
    user: Annotated[UserContext, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_admin_tenant_session)],
) -> list[ContentResponse]:
    items = await content_repo.list_by_tenant(
        session=session,
        tenant_id=user.tenant_id,  # type: ignore[arg-type]
    )
    return [
        ContentResponse(
            id=item.id,
            tenant_id=item.tenant_id,
            title=item.title,
            body=item.body,
            content_type=item.content_type,
            created_at=item.created_at.isoformat(),
            updated_at=item.updated_at.isoformat(),
        )
        for item in items
    ]


@router.put("/{content_id}", response_model=ContentResponse)
async def update_content(
    content_id: UUID,
    body: ContentUpdate,
    user: Annotated[UserContext, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_admin_tenant_session)],
) -> ContentResponse:
    item = await content_repo.update(
        session=session,
        tenant_id=user.tenant_id,  # type: ignore[arg-type]
        content_id=content_id,
        title=body.title,
        body=body.body,
        content_type=body.content_type,
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content item not found",
        )
    return ContentResponse(
        id=item.id,
        tenant_id=item.tenant_id,
        title=item.title,
        body=item.body,
        content_type=item.content_type,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
    )


@router.delete("/{content_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_content(
    content_id: UUID,
    user: Annotated[UserContext, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_admin_tenant_session)],
) -> None:
    deleted = await content_repo.delete_by_id(
        session=session,
        tenant_id=user.tenant_id,  # type: ignore[arg-type]
        content_id=content_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content item not found",
        )
