from uuid import uuid4

import pytest

from app.schemas import RAGSearchOutput, ToolError
from app.services.rag import RAGService, RetrievedChunk


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
