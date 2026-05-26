"""Content item repository — CRUD for tenant-scoped content."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentItem


async def create(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    title: str,
    body: str,
    content_type: str,
) -> ContentItem:
    item = ContentItem(
        tenant_id=tenant_id, title=title, body=body, content_type=content_type
    )
    session.add(item)
    await session.flush()
    await session.refresh(item)
    return item


async def get_by_id(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    content_id: uuid.UUID,
) -> ContentItem | None:
    result = await session.execute(
        select(ContentItem).where(
            ContentItem.id == content_id,
            ContentItem.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def list_by_tenant(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> list[ContentItem]:
    result = await session.execute(
        select(ContentItem)
        .where(ContentItem.tenant_id == tenant_id)
        .order_by(ContentItem.created_at.desc())
    )
    return list(result.scalars().all())


async def update(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    content_id: uuid.UUID,
    *,
    title: str | None = None,
    body: str | None = None,
    content_type: str | None = None,
) -> ContentItem | None:
    item = await get_by_id(session, tenant_id, content_id)
    if item is None:
        return None
    if title is not None:
        item.title = title
    if body is not None:
        item.body = body
    if content_type is not None:
        item.content_type = content_type
    await session.flush()
    return item


async def delete_by_id(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    content_id: uuid.UUID,
) -> bool:
    result = await session.execute(
        delete(ContentItem).where(
            ContentItem.id == content_id,
            ContentItem.tenant_id == tenant_id,
        )
    )
    return result.rowcount > 0


async def delete_by_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Delete all content for a tenant. Called by the erasure service."""
    result = await session.execute(
        delete(ContentItem).where(ContentItem.tenant_id == tenant_id)
    )
    return result.rowcount
