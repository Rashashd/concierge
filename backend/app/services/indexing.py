"""Content indexing service — embed content items and sync MinIO blobs."""

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.minio import MinioClient
from app.repositories import chunks as chunk_repo
from app.repositories import content as content_repo

logger = structlog.get_logger(__name__)


async def _embed_item(
    session: AsyncSession,
    embeddings: Any,
    tenant_id: UUID,
    content_id: UUID,
    title: str,
    body: str,
) -> None:
    """Delete existing chunks for a content item then write fresh embeddings."""
    embed_fn = getattr(embeddings, "aembed_documents", None)
    if embed_fn is None:
        logger.warning("indexing.embeddings_unavailable", content_id=str(content_id))
        return
    text = f"{title}\n\n{body}"
    vectors: list[list[float]] = await embed_fn([text])
    await chunk_repo.delete_by_content_item(session, tenant_id, content_id)
    await chunk_repo.create_bulk(
        session,
        tenant_id=tenant_id,
        content_item_id=content_id,
        texts=[text],
        embeddings=vectors,
    )
    logger.info("indexing.item_embedded", content_id=str(content_id))


async def index_content(
    session: AsyncSession,
    embeddings: Any,
    minio: MinioClient,
    tenant_id: UUID,
    content_id: UUID,
    title: str,
    body: str,
    content_type: str,
) -> None:
    """Write blob to MinIO and embed into pgvector. Called on create and update."""
    await minio.put_content(
        tenant_id=tenant_id,
        content_id=content_id,
        payload={
            "id": str(content_id),
            "tenant_id": str(tenant_id),
            "title": title,
            "body": body,
            "content_type": content_type,
        },
    )
    await _embed_item(session, embeddings, tenant_id, content_id, title, body)


async def reindex_tenant(
    session: AsyncSession,
    embeddings: Any,
    tenant_id: UUID,
) -> None:
    """Re-embed all content items for a tenant. Idempotent — safe to re-run."""
    items = await content_repo.list_by_tenant(session, tenant_id)
    for item in items:
        await _embed_item(
            session, embeddings, tenant_id, item.id, item.title, item.body
        )
    logger.info("indexing.tenant_reindexed", tenant_id=str(tenant_id), count=len(items))
