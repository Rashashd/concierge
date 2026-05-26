"""Chunk repository — bulk insert and pgvector cosine similarity search."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk


async def create_bulk(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    content_item_id: uuid.UUID,
    texts: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict] | None = None,
) -> list[Chunk]:
    """Insert all chunks for a content item in one flush.

    metadatas must be the same length as texts if provided.
    """
    if metadatas is None:
        metadatas = [{} for _ in texts]
    chunks = [
        Chunk(
            tenant_id=tenant_id,
            content_item_id=content_item_id,
            chunk_index=i,
            text=text,
            embedding=embedding,
            chunk_metadata=meta,
        )
        for i, (text, embedding, meta) in enumerate(
            zip(texts, embeddings, metadatas, strict=True)
        )
    ]
    session.add_all(chunks)
    await session.flush()
    return chunks


async def search(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query_embedding: list[float],
    k: int = 5,
) -> list[Chunk]:
    """Return the k most relevant chunks for a query using cosine distance.

    Filters by tenant_id in addition to RLS (belt + suspenders).
    """
    result = await session.execute(
        select(Chunk)
        .where(Chunk.tenant_id == tenant_id)
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(k)
    )
    return list(result.scalars().all())


async def delete_by_content_item(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    content_item_id: uuid.UUID,
) -> int:
    """Delete all chunks for a content item (called on update or delete)."""
    result = await session.execute(
        delete(Chunk).where(
            Chunk.content_item_id == content_item_id,
            Chunk.tenant_id == tenant_id,
        )
    )
    return result.rowcount


async def delete_by_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Delete all chunks for a tenant. Called by the erasure service."""
    result = await session.execute(delete(Chunk).where(Chunk.tenant_id == tenant_id))
    return result.rowcount
