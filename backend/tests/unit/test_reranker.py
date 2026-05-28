from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.services.rag import (
    RAGService,
    RetrievedChunk,
    _rerank_candidate_count,
    build_pgvector_rag_service,
)
from app.services.reranker import (
    CohereReranker,
    LLMReranker,
    RerankCandidate,
    RerankDecision,
    Reranker,
    _fallback_decisions,
    _validate_decisions,
    build_reranker,
)


class FakeEmbeddings:
    async def aembed_query(self, query: str) -> list[float]:
        return [0.1, 0.2, 0.3]


class FakeReranker(Reranker):
    def __init__(
        self,
        decisions: list[RerankDecision] | None = None,
        raise_on_rerank: bool = False,
    ) -> None:
        self._decisions = decisions
        self._raise = raise_on_rerank
        self.call_count = 0
        self.last_query: str | None = None
        self.last_candidates: list[RerankCandidate] | None = None

    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankDecision]:
        self.call_count += 1
        self.last_query = query
        self.last_candidates = candidates
        if self._raise:
            raise RuntimeError("reranker failed")
        if self._decisions is not None:
            return self._decisions
        return _fallback_decisions(candidates)


@pytest.mark.asyncio
async def test_rag_service_without_reranker_preserves_current_behavior() -> None:
    tenant_id = uuid4()
    content_item_id = uuid4()
    chunk_id = uuid4()
    received_top_k: list[int] = []

    async def retrieve_chunks(
        received_tenant_id: object,
        query: object,
        embedding: object,
        top_k: int,
    ) -> list[RetrievedChunk]:
        received_top_k.append(top_k)
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
        reranker=None,
    )

    result = await service.search(
        tenant_id=tenant_id,
        query="What are your hours?",
        top_k=5,
    )

    assert received_top_k == [5]
    assert len(result.source_chunks) == 1


@pytest.mark.asyncio
async def test_rag_service_with_reranker_retrieves_more_candidates() -> None:
    tenant_id = uuid4()
    chunk_ids = [uuid4() for _ in range(20)]
    content_item_id = uuid4()
    received_top_k: list[int] = []

    async def retrieve_chunks(
        received_tenant_id: object,
        query: object,
        embedding: object,
        top_k: int,
    ) -> list[RetrievedChunk]:
        received_top_k.append(top_k)
        return [
            RetrievedChunk(
                chunk_id=chunk_ids[i],
                content_item_id=content_item_id,
                text=f"Chunk {i}",
                score=0.9 - i * 0.01,
            )
            for i in range(top_k)
        ]

    reranker = FakeReranker()
    service = RAGService(
        embeddings_client=FakeEmbeddings(),
        chunk_retriever=retrieve_chunks,
        reranker=reranker,
    )

    await service.search(
        tenant_id=tenant_id,
        query="What are your hours?",
        top_k=5,
    )

    assert received_top_k == [20]
    assert reranker.call_count == 1


@pytest.mark.asyncio
async def test_reranker_output_changes_final_chunk_order() -> None:
    tenant_id = uuid4()
    total_candidates = 10
    chunk_ids = [uuid4() for _ in range(total_candidates)]
    content_item_id = uuid4()

    async def retrieve_chunks(
        received_tenant_id: object,
        query: object,
        embedding: object,
        top_k: int,
    ) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id=chunk_ids[i],
                content_item_id=content_item_id,
                text=f"Chunk {i}",
                score=0.9 - i * 0.01,
            )
            for i in range(total_candidates)
        ]

    reversed_decisions = [
        RerankDecision(index=9, score=0.9),
        RerankDecision(index=8, score=0.8),
        RerankDecision(index=7, score=0.7),
        RerankDecision(index=6, score=0.6),
        RerankDecision(index=5, score=0.5),
        RerankDecision(index=4, score=0.4),
        RerankDecision(index=3, score=0.3),
        RerankDecision(index=2, score=0.2),
        RerankDecision(index=1, score=0.1),
        RerankDecision(index=0, score=0.0),
    ]
    reranker = FakeReranker(decisions=reversed_decisions)
    service = RAGService(
        embeddings_client=FakeEmbeddings(),
        chunk_retriever=retrieve_chunks,
        reranker=reranker,
    )

    result = await service.search(
        tenant_id=tenant_id,
        query="What are your hours?",
        top_k=5,
    )

    assert result.source_chunks[0].chunk_id == chunk_ids[9]
    assert result.source_chunks[-1].chunk_id == chunk_ids[5]


@pytest.mark.asyncio
async def test_reranker_invalid_output_falls_back_to_vector_order() -> None:
    tenant_id = uuid4()
    total_candidates = 6
    chunk_ids = [uuid4() for _ in range(total_candidates)]
    content_item_id = uuid4()

    async def retrieve_chunks(
        received_tenant_id: object,
        query: object,
        embedding: object,
        top_k: int,
    ) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id=chunk_ids[i],
                content_item_id=content_item_id,
                text=f"Chunk {i}",
                score=0.9 - i * 0.01,
            )
            for i in range(total_candidates)
        ]

    decisions_with_bad_indexes = [
        RerankDecision(index=99, score=1.0),
        RerankDecision(index=100, score=0.9),
    ]
    reranker = FakeReranker(decisions=decisions_with_bad_indexes)
    service = RAGService(
        embeddings_client=FakeEmbeddings(),
        chunk_retriever=retrieve_chunks,
        reranker=reranker,
    )

    result = await service.search(
        tenant_id=tenant_id,
        query="What are your hours?",
        top_k=5,
    )

    assert len(result.source_chunks) == 5
    assert result.source_chunks[0].chunk_id == chunk_ids[0]


@pytest.mark.asyncio
async def test_reranker_failure_falls_back_to_vector_order() -> None:
    tenant_id = uuid4()
    total_candidates = 6
    chunk_ids = [uuid4() for _ in range(total_candidates)]
    content_item_id = uuid4()

    async def retrieve_chunks(
        received_tenant_id: object,
        query: object,
        embedding: object,
        top_k: int,
    ) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id=chunk_ids[i],
                content_item_id=content_item_id,
                text=f"Chunk {i}",
                score=0.9 - i * 0.01,
            )
            for i in range(total_candidates)
        ]

    reranker = FakeReranker(raise_on_rerank=True)
    service = RAGService(
        embeddings_client=FakeEmbeddings(),
        chunk_retriever=retrieve_chunks,
        reranker=reranker,
    )

    result = await service.search(
        tenant_id=tenant_id,
        query="What are your hours?",
        top_k=5,
    )

    assert len(result.source_chunks) == 5
    assert result.source_chunks[0].chunk_id == chunk_ids[0]


@pytest.mark.asyncio
async def test_tenant_id_passed_into_retriever_with_reranker() -> None:
    tenant_id = uuid4()
    chunk_ids = [uuid4() for _ in range(20)]
    content_item_id = uuid4()
    received_tenants: list[object] = []

    async def retrieve_chunks(
        received_tenant_id: object,
        query: object,
        embedding: object,
        top_k: int,
    ) -> list[RetrievedChunk]:
        received_tenants.append(received_tenant_id)
        return [
            RetrievedChunk(
                chunk_id=chunk_ids[i],
                content_item_id=content_item_id,
                text=f"Chunk {i}",
                score=0.9 - i * 0.01,
            )
            for i in range(20)
        ]

    reranker = FakeReranker()
    service = RAGService(
        embeddings_client=FakeEmbeddings(),
        chunk_retriever=retrieve_chunks,
        reranker=reranker,
    )

    await service.search(
        tenant_id=tenant_id,
        query="What are your hours?",
        top_k=5,
    )

    assert received_tenants == [tenant_id]
    assert reranker.last_query == "What are your hours?"


def test_rerank_candidate_count_formula() -> None:
    assert _rerank_candidate_count(1) == 12
    assert _rerank_candidate_count(3) == 12
    assert _rerank_candidate_count(5) == 20
    assert _rerank_candidate_count(10) == 20


def test_fallback_decisions_preserves_all_candidates() -> None:
    candidates = [
        RerankCandidate(index=0, chunk_id="a", text="x"),
        RerankCandidate(index=1, chunk_id="b", text="y"),
    ]
    decisions = _fallback_decisions(candidates)
    assert len(decisions) == 2
    assert {d.index for d in decisions} == {0, 1}
    assert all(d.score == 0.5 for d in decisions)


def test_validate_decisions_filters_invalid_indexes() -> None:
    candidates = [
        RerankCandidate(index=0, chunk_id="a", text="x"),
        RerankCandidate(index=1, chunk_id="b", text="y"),
    ]

    decisions = [
        RerankDecision(index=0, score=0.8),
        RerankDecision(index=99, score=1.0),
    ]

    result = _validate_decisions(decisions, candidates)
    assert len(result) == 2
    assert result[0].index == 0
    assert result[1].index == 1
    assert result[1].score == 0.0


def test_validate_decisions_deduplicates() -> None:
    candidates = [
        RerankCandidate(index=0, chunk_id="a", text="x"),
        RerankCandidate(index=1, chunk_id="b", text="y"),
    ]

    decisions = [
        RerankDecision(index=0, score=0.8),
        RerankDecision(index=0, score=0.9),
        RerankDecision(index=1, score=0.7),
    ]

    result = _validate_decisions(decisions, candidates)
    assert len(result) == 2
    assert result[0].index == 0
    assert result[0].score == 0.8


@pytest.mark.asyncio
async def test_cohere_reranker_maps_remote_indexes_to_candidate_indexes() -> None:
    class FakeCohereClient:
        async def rerank(self, **kwargs: object) -> SimpleNamespace:
            assert kwargs["model"] == "rerank-v4.0-fast"
            assert kwargs["query"] == "refund rules"
            assert kwargs["documents"] == ["archived refund rules", "current refund"]
            assert kwargs["top_n"] == 2
            return SimpleNamespace(
                results=[
                    SimpleNamespace(index=1, relevance_score=0.91),
                    SimpleNamespace(index=0, relevance_score=0.2),
                ]
            )

    reranker = CohereReranker(
        api_key="test-key",
        model="rerank-v4.0-fast",
        timeout_seconds=5,
        max_retries=0,
        client=FakeCohereClient(),
    )
    decisions = await reranker.rerank(
        query="refund rules",
        candidates=[
            RerankCandidate(index=10, chunk_id="a", text="archived refund rules"),
            RerankCandidate(index=11, chunk_id="b", text="current refund"),
        ],
    )

    assert decisions[0] == RerankDecision(index=11, score=0.91)
    assert decisions[1] == RerankDecision(index=10, score=0.2)


@pytest.mark.asyncio
async def test_cohere_reranker_failure_falls_back() -> None:
    class BrokenCohereClient:
        async def rerank(self, **kwargs: object) -> object:
            raise RuntimeError("remote error")

    candidates = [
        RerankCandidate(index=0, chunk_id="a", text="first"),
        RerankCandidate(index=1, chunk_id="b", text="second"),
    ]
    reranker = CohereReranker(
        api_key="test-key",
        model="rerank-v4.0-fast",
        timeout_seconds=5,
        max_retries=0,
        client=BrokenCohereClient(),
    )

    decisions = await reranker.rerank(query="anything", candidates=candidates)

    assert decisions == _fallback_decisions(candidates)


def test_build_reranker_defaults_to_llm_provider() -> None:
    settings = Settings(vault_addr="http://vault:8200", vault_token=SecretStr("x"))
    reranker = build_reranker(settings=settings, llm=object())
    assert isinstance(reranker, LLMReranker)


def test_build_reranker_uses_cohere_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    received: dict[str, object] = {}

    def fake_cohere_reranker(**kwargs: object) -> object:
        received.update(kwargs)
        return sentinel

    monkeypatch.setattr(
        "app.services.reranker.CohereReranker",
        fake_cohere_reranker,
    )
    settings = Settings(
        vault_addr="http://vault:8200",
        vault_token=SecretStr("x"),
        reranker_provider="cohere",
        cohere_api_key=SecretStr("test-key"),
    )
    reranker = build_reranker(settings=settings, llm=object())
    assert reranker is sentinel
    assert received["api_key"] == "test-key"
    assert received["model"] == "rerank-v4.0-fast"
    assert received["max_retries"] == 2


@pytest.mark.asyncio
async def test_pgvector_rag_service_with_reranker_retrieves_larger_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid4()
    content_item_id = uuid4()
    chunk_ids = [uuid4() for _ in range(20)]
    received_k: list[int] = []

    async def fake_search_with_scores(
        session: object,
        tenant_id: object,
        query_embedding: object,
        k: object,
    ) -> list[tuple[SimpleNamespace, float]]:
        received_k.append(k)
        return [
            (
                SimpleNamespace(
                    id=chunk_ids[i],
                    content_item_id=content_item_id,
                    text=f"Chunk {i}",
                ),
                0.9 - i * 0.01,
            )
            for i in range(k)
        ]

    monkeypatch.setattr(
        "app.services.rag.chunk_repo.search_with_scores",
        fake_search_with_scores,
    )

    reranker = FakeReranker()
    session = object()
    service = build_pgvector_rag_service(
        session=cast(object, session),
        embeddings_client=FakeEmbeddings(),
        reranker=reranker,
    )

    result = await service.search(
        tenant_id=tenant_id,
        query="What are your hours?",
        top_k=5,
    )

    assert received_k == [20]
    assert reranker.call_count == 1
    assert len(result.source_chunks) == 5
