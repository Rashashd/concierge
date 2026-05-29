"""Integration tests for chunks repository — SQL generation and hybrid logic."""

from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import chunks as chunk_repo


@pytest.mark.asyncio
async def test_keyword_search_filters_by_tenant_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.repositories.chunks import keyword_search as repo_keyword_search

    tenant_id = uuid4()
    chunk_id = uuid4()
    content_item_id = uuid4()
    received: dict[str, object] = {}

    class FakeSession:
        async def execute(self, stmt: object) -> SimpleNamespace:
            received["stmt"] = stmt
            return SimpleNamespace(
                all=lambda: [
                    (
                        SimpleNamespace(
                            id=chunk_id,
                            content_item_id=content_item_id,
                            text="matching text",
                        ),
                        0.42,
                    )
                ]
            )

    await repo_keyword_search(
        session=cast(AsyncSession, FakeSession()),
        tenant_id=tenant_id,
        query="matching",
        k=5,
    )

    stmt = received["stmt"]
    where_str = str(stmt.whereclause)
    assert "tenant_id" in where_str
    assert "chunks.tenant_id" in where_str


@pytest.mark.asyncio
async def test_hybrid_deduplicates_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    content_item_id = uuid4()
    chunk_a = uuid4()
    chunk_b = uuid4()

    async def fake_vector(*args: object, **kwargs: object) -> list[tuple]:
        return [
            (
                SimpleNamespace(id=chunk_a, content_item_id=content_item_id, text="A"),
                0.9,
            ),
            (
                SimpleNamespace(id=chunk_b, content_item_id=content_item_id, text="B"),
                0.7,
            ),
        ]

    async def fake_keyword(*args: object, **kwargs: object) -> list[tuple]:
        return [
            (
                SimpleNamespace(id=chunk_a, content_item_id=content_item_id, text="A"),
                0.8,
            ),
        ]

    from app.repositories.chunks import hybrid_search as repo_hybrid_search

    monkeypatch.setattr(chunk_repo, "search_with_scores", fake_vector)
    monkeypatch.setattr(chunk_repo, "keyword_search", fake_keyword)

    results = await repo_hybrid_search(
        session=cast(AsyncSession, object()),
        tenant_id=tenant_id,
        query_embedding=[0.1],
        query="test",
        vector_weight=0.5,
        keyword_weight=0.5,
        vector_k=10,
        keyword_k=10,
    )

    assert len(results) == 2
    chunk_ids = {chunk.id for chunk, score in results}
    assert chunk_ids == {chunk_a, chunk_b}


@pytest.mark.asyncio
async def test_hybrid_scoring_respects_weights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    content_item_id = uuid4()
    chunk_a = uuid4()
    chunk_b = uuid4()

    async def fake_vector(*args: object, **kwargs: object) -> list[tuple]:
        return [
            (
                SimpleNamespace(id=chunk_a, content_item_id=content_item_id, text="A"),
                1.0,
            ),
            (
                SimpleNamespace(id=chunk_b, content_item_id=content_item_id, text="B"),
                0.0,
            ),
        ]

    async def fake_keyword(*args: object, **kwargs: object) -> list[tuple]:
        return [
            (
                SimpleNamespace(id=chunk_b, content_item_id=content_item_id, text="B"),
                1.0,
            ),
        ]

    from app.repositories.chunks import hybrid_search as repo_hybrid_search

    monkeypatch.setattr(chunk_repo, "search_with_scores", fake_vector)
    monkeypatch.setattr(chunk_repo, "keyword_search", fake_keyword)

    results = await repo_hybrid_search(
        session=cast(AsyncSession, object()),
        tenant_id=tenant_id,
        query_embedding=[0.1],
        query="test",
        vector_weight=0.9,
        keyword_weight=0.1,
        vector_k=10,
        keyword_k=10,
    )

    assert len(results) == 2
    assert results[0][0].id == chunk_a
    assert results[1][0].id == chunk_b
