from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import RAGSearchInput, RAGSearchOutput
from app.services.rag import RAGService, RetrievedChunk
from app.tools.rag_search import rag_search


def test_rag_search_input_rejects_tenant_id() -> None:
    with pytest.raises(ValidationError):
        RAGSearchInput.model_validate(
            {
                "query": "What are your hours?",
                "top_k": 5,
                "tenant_id": str(uuid4()),
            }
        )


@pytest.mark.asyncio
async def test_rag_search_uses_injected_tenant_id() -> None:
    tenant_id = uuid4()
    content_item_id = uuid4()
    chunk_id = uuid4()

    class FakeEmbeddings:
        async def aembed_query(self, query: str) -> list[float]:
            return [0.4, 0.5]

    async def retrieve_chunks(
        received_tenant_id: object,
        embedding: object,
        top_k: object,
    ) -> list[RetrievedChunk]:
        assert received_tenant_id == tenant_id
        assert embedding == [0.4, 0.5]
        assert top_k == 5
        return [
            RetrievedChunk(
                chunk_id=chunk_id,
                content_item_id=content_item_id,
                text="Tenant-scoped answer.",
                score=0.9,
            )
        ]

    result = await rag_search(
        tenant_id=tenant_id,
        tool_input=RAGSearchInput(query="What are your hours?"),
        rag_service=RAGService(
            embeddings_client=FakeEmbeddings(),
            chunk_retriever=retrieve_chunks,
        ),
    )

    assert isinstance(result, RAGSearchOutput)
    assert result.source_chunks
    assert result.source_chunks[0].chunk_id == chunk_id
