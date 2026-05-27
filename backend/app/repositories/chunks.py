"""Chunk repository — bulk insert, pgvector search, keyword & hybrid search."""

import uuid

from sqlalchemy import delete, func, select
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


async def search_with_scores(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query_embedding: list[float],
    k: int = 5,
) -> list[tuple[Chunk, float]]:
    """Return chunks with cosine similarity scores for RAG citations."""
    distance = Chunk.embedding.cosine_distance(query_embedding)
    result = await session.execute(
        select(Chunk, distance.label("distance"))
        .where(Chunk.tenant_id == tenant_id)
        .order_by(distance)
        .limit(k)
    )
    return [
        (chunk, max(0.0, 1.0 - float(cosine_distance)))
        for chunk, cosine_distance in result.all()
    ]


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


async def keyword_search(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query: str,
    k: int = 20,
) -> list[tuple[Chunk, float]]:
    """Keyword search using Postgres full-text search with ts_rank_cd.

    Filters by tenant_id in addition to RLS (belt + suspenders).
    """
    ts_vector = func.to_tsvector("english", Chunk.text)
    ts_query = func.plainto_tsquery("english", query)
    rank = func.ts_rank_cd(ts_vector, ts_query)
    result = await session.execute(
        select(Chunk, rank.label("rank"))
        .where(Chunk.tenant_id == tenant_id, ts_vector.op("@@")(ts_query))
        .order_by(rank.desc())
        .limit(k)
    )
    return [(chunk, float(rank_val)) for chunk, rank_val in result.all()]


async def hybrid_search(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query_embedding: list[float],
    query: str,
    vector_weight: float = 0.7,
    keyword_weight: float = 0.3,
    vector_k: int = 20,
    keyword_k: int = 20,
) -> list[tuple[Chunk, float]]:
    """Merge vector and keyword results by chunk id, normalize scores, and
    combine with weighted sum. Tenant-filtered at both query legs.
    """
    vector_results = await search_with_scores(
        session, tenant_id, query_embedding, vector_k
    )
    keyword_results = await keyword_search(session, tenant_id, query, keyword_k)

    scores: dict[uuid.UUID, tuple[Chunk, float, float]] = {}
    for chunk, vec_score in vector_results:
        scores[chunk.id] = (chunk, vec_score, 0.0)
    for chunk, kw_score in keyword_results:
        if chunk.id in scores:
            existing_chunk, existing_vs, _ = scores[chunk.id]
            scores[chunk.id] = (existing_chunk, existing_vs, kw_score)
        else:
            scores[chunk.id] = (chunk, 0.0, kw_score)

    combined: list[tuple[Chunk, float]] = []
    for chunk, vs, ks in scores.values():
        vs_norm = max(0.0, min(1.0, vs))
        ks_norm = max(0.0, min(1.0, ks))
        combined_score = vector_weight * vs_norm + keyword_weight * ks_norm
        combined.append((chunk, combined_score))

    combined.sort(key=lambda pair: pair[1], reverse=True)
    return combined
