"""User repository — thin SQL wrappers for admin operations outside fastapi-users."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


async def get_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def list_by_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> list[User]:
    result = await session.execute(
        select(User).where(User.tenant_id == tenant_id).order_by(User.created_at)
    )
    return list(result.scalars().all())


async def get_emails_by_ids(
    session: AsyncSession,
    user_ids: set[uuid.UUID],
) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    result = await session.execute(
        select(User.id, User.email).where(User.id.in_(user_ids))
    )
    return {row.id: row.email for row in result}


async def delete_by_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    result = await session.execute(select(User).where(User.tenant_id == tenant_id))
    users = list(result.scalars().all())
    for user in users:
        await session.delete(user)
    return len(users)
