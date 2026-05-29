from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import chunks as chunk_repo
from app.schemas import RAGSearchOutput, ToolError
from app.services.rag import RAGService, RetrievedChunk, build_pgvector_rag_service
from app.services.reranker import RerankCandidate, RerankDecision, Reranker


class FakeEmbeddings:
    async def aembed_query(self, query: str) -> list[float]:
        assert query == "What are your hours?"
        return [0.1, 0.2, 0.3]


@pytest.mark.asyncio
async def test_rag_service_injects_tenant_id_into_retriever() -> None:
    tenant_id = uuid4()
    content_item_id = uuid4()
    chunk_id = uuid4()
    calls: list[tuple[object, object, object]] = []

    async def retrieve_chunks(
        received_tenant_id: object,
        query: object,
        embedding: object,
        top_k: object,
    ) -> list[RetrievedChunk]:
        calls.append((received_tenant_id, embedding, top_k))
        return [
            RetrievedChunk(
                chunk_id=chunk_id,
                content_item_id=content_item_id,
                text="We are open Monday to Friday.",
                score=0.98,
            )
        ]

    service = RAGService(
        embeddings_client=FakeEmbeddings(),
        chunk_retriever=retrieve_chunks,
    )

    result = await service.search(
        tenant_id=tenant_id,
        query="What are your hours?",
        top_k=3,
    )

    assert isinstance(result, RAGSearchOutput)
    assert calls == [(tenant_id, [0.1, 0.2, 0.3], 3)]
    assert result.source_chunks[0].chunk_id == chunk_id
    assert "Monday to Friday" in result.answer


@pytest.mark.asyncio
async def test_rag_service_returns_tool_error_when_unwired() -> None:
    service = RAGService(embeddings_client=None, chunk_retriever=None)

    result = await service.search(
        tenant_id=uuid4(),
        query="What are your hours?",
        top_k=3,
    )

    assert isinstance(result, ToolError)
    assert result.code == "retrieval_unavailable"


@pytest.mark.asyncio
async def test_rag_service_returns_no_chunks_error() -> None:
    async def retrieve_chunks(
        received_tenant_id: object,
        query: object,
        embedding: object,
        top_k: object,
    ) -> list[RetrievedChunk]:
        return []

    service = RAGService(
        embeddings_client=FakeEmbeddings(),
        chunk_retriever=retrieve_chunks,
    )

    result = await service.search(
        tenant_id=uuid4(),
        query="What are your hours?",
        top_k=3,
    )

    assert isinstance(result, ToolError)
    assert result.code == "no_chunks_found"


@pytest.mark.asyncio
async def test_pgvector_rag_service_uses_tenant_scoped_chunk_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    content_item_id = uuid4()
    chunk_id = uuid4()
    calls: list[tuple[object, object, object, object]] = []

    async def fake_search_with_scores(
        session: object,
        tenant_id: object,
        query_embedding: object,
        k: object,
    ) -> list[tuple[SimpleNamespace, float]]:
        calls.append((session, tenant_id, query_embedding, k))
        return [
            (
                SimpleNamespace(
                    id=chunk_id,
                    content_item_id=content_item_id,
                    text="Tenant-scoped repository result.",
                ),
                0.82,
            )
        ]

    monkeypatch.setattr(
        "app.services.rag.chunk_repo.search_with_scores",
        fake_search_with_scores,
    )

    session = object()
    service = build_pgvector_rag_service(
        session=cast(AsyncSession, session),
        embeddings_client=FakeEmbeddings(),
    )

    result = await service.search(
        tenant_id=tenant_id,
        query="What are your hours?",
        top_k=3,
    )

    assert isinstance(result, RAGSearchOutput)
    assert calls == [(session, tenant_id, [0.1, 0.2, 0.3], 3)]
    assert result.source_chunks[0].chunk_id == chunk_id
    assert result.source_chunks[0].score == 0.82


class FakeReranker(Reranker):
    def __init__(self) -> None:
        self.call_count = 0
        self.last_candidates: list[RerankCandidate] | None = None

    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankDecision]:
        self.call_count += 1
        self.last_candidates = candidates
        return [
            RerankDecision(index=c.index, score=0.9 - c.index * 0.01)
            for c in candidates
        ]


@pytest.mark.asyncio
async def test_vector_mode_calls_search_with_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    content_item_id = uuid4()
    chunk_id = uuid4()
    vector_calls: list[tuple] = []
    keyword_calls: list[tuple] = []

    async def fake_search_with_scores(
        session: object,
        tenant_id: object,
        query_embedding: object,
        k: object,
    ) -> list[tuple[SimpleNamespace, float]]:
        vector_calls.append((tenant_id, k))
        return [
            (
                SimpleNamespace(id=chunk_id, content_item_id=content_item_id, text="x"),
                0.82,
            )
        ]

    async def fake_keyword_search(
        session: object,
        tenant_id: object,
        query: object,
        k: object,
    ) -> list[tuple[SimpleNamespace, float]]:
        keyword_calls.append((tenant_id, k))
        return []

    monkeypatch.setattr(chunk_repo, "search_with_scores", fake_search_with_scores)
    monkeypatch.setattr(chunk_repo, "keyword_search", fake_keyword_search)

    session = object()
    service = build_pgvector_rag_service(
        session=cast(AsyncSession, session),
        embeddings_client=FakeEmbeddings(),
        retrieval_mode="vector",
    )

    await service.search(
        tenant_id=tenant_id,
        query="What are your hours?",
        top_k=5,
    )

    assert len(vector_calls) == 1
    assert vector_calls[0] == (tenant_id, 5)
    assert keyword_calls == []


@pytest.mark.asyncio
async def test_hybrid_mode_calls_hybrid_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    content_item_id = uuid4()
    chunk_id = uuid4()
    hybrid_calls: list[tuple] = []
    vector_calls: list[tuple] = []

    async def fake_hybrid_search(
        session: object,
        tenant_id: object,
        query_embedding: object,
        query: object,
        vector_weight: float,
        keyword_weight: float,
        vector_k: int,
        keyword_k: int,
    ) -> list[tuple[SimpleNamespace, float]]:
        hybrid_calls.append(
            (tenant_id, query, vector_weight, keyword_weight, vector_k, keyword_k)
        )
        return [
            (
                SimpleNamespace(id=chunk_id, content_item_id=content_item_id, text="x"),
                0.85,
            )
        ]

    async def fake_search_with_scores(
        session: object,
        tenant_id: object,
        query_embedding: object,
        k: object,
    ) -> list[tuple[SimpleNamespace, float]]:
        vector_calls.append((tenant_id, k))
        return []

    monkeypatch.setattr(chunk_repo, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(chunk_repo, "search_with_scores", fake_search_with_scores)

    session = object()
    service = build_pgvector_rag_service(
        session=cast(AsyncSession, session),
        embeddings_client=FakeEmbeddings(),
        retrieval_mode="hybrid",
        hybrid_vector_weight=0.7,
        hybrid_keyword_weight=0.3,
        hybrid_vector_candidate_count=20,
        hybrid_keyword_candidate_count=20,
    )

    await service.search(
        tenant_id=tenant_id,
        query="What are your hours?",
        top_k=5,
    )

    assert len(hybrid_calls) == 1
    assert hybrid_calls[0] == (tenant_id, "What are your hours?", 0.7, 0.3, 20, 20)
    assert vector_calls == []


@pytest.mark.asyncio
async def test_hybrid_mode_with_reranker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    content_item_id = uuid4()
    chunk_ids = [uuid4() for _ in range(10)]

    async def fake_hybrid_search(
        session: object,
        tenant_id: object,
        query_embedding: object,
        query: object,
        vector_weight: float,
        keyword_weight: float,
        vector_k: int,
        keyword_k: int,
    ) -> list[tuple[SimpleNamespace, float]]:
        return [
            (
                SimpleNamespace(
                    id=chunk_ids[i],
                    content_item_id=content_item_id,
                    text=f"Chunk {i}",
                ),
                0.9 - i * 0.08,
            )
            for i in range(10)
        ]

    async def fake_search_with_scores(*args: object, **kwargs: object) -> list:
        return []

    monkeypatch.setattr(chunk_repo, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(chunk_repo, "search_with_scores", fake_search_with_scores)

    reranker = FakeReranker()
    session = object()
    service = build_pgvector_rag_service(
        session=cast(AsyncSession, session),
        embeddings_client=FakeEmbeddings(),
        reranker=reranker,
        retrieval_mode="hybrid",
    )

    result = await service.search(
        tenant_id=tenant_id,
        query="What are your hours?",
        top_k=5,
    )

    assert reranker.call_count == 1
    assert reranker.last_candidates is not None
    for candidate in reranker.last_candidates:
        assert "tenant_id" not in candidate.model_dump()
    assert len(result.source_chunks) == 5
