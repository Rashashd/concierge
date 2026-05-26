from uuid import NAMESPACE_URL, UUID, uuid5

from app.schemas import ChunkReference, RAGSearchInput, RAGSearchOutput, ToolError

TOOL_NAME = "rag_search"


async def rag_search(
    tenant_id: UUID,
    tool_input: RAGSearchInput,
) -> RAGSearchOutput | ToolError:
    if not tool_input.query.strip():
        return ToolError(
            tool=TOOL_NAME,
            code="validation_error",
            message="Search query cannot be empty.",
        )

    chunk_id = uuid5(NAMESPACE_URL, f"{tenant_id}:rag-search:stub-chunk")
    content_item_id = uuid5(NAMESPACE_URL, f"{tenant_id}:rag-search:stub-content")
    answer = (
        "I found a placeholder tenant-scoped result. Real CMS retrieval will replace "
        "this stub after the chunk repository and embeddings are wired."
    )

    return RAGSearchOutput(
        answer=answer,
        source_chunks=[
            ChunkReference(
                chunk_id=chunk_id,
                content_item_id=content_item_id,
                text=f"Tenant-scoped placeholder result for: {tool_input.query}",
                score=1.0,
            )
        ],
    )
