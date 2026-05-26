from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import RAGSearchInput, RAGSearchOutput
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

    result = await rag_search(
        tenant_id=tenant_id,
        tool_input=RAGSearchInput(query="What are your hours?"),
    )

    assert isinstance(result, RAGSearchOutput)
    assert result.source_chunks
    assert "What are your hours?" in result.source_chunks[0].text
