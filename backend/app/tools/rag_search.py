from uuid import UUID

from app.schemas import RAGSearchInput, RAGSearchOutput, ToolError
from app.services.rag import RAGService, build_unwired_rag_service

TOOL_NAME = "rag_search"


async def rag_search(
    tenant_id: UUID,
    tool_input: RAGSearchInput,
    rag_service: RAGService | None = None,
) -> RAGSearchOutput | ToolError:
    if not tool_input.query.strip():
        return ToolError(
            tool=TOOL_NAME,
            code="validation_error",
            message="Search query cannot be empty.",
        )

    service = rag_service or build_unwired_rag_service()
    return await service.search(
        tenant_id=tenant_id,
        query=tool_input.query,
        top_k=tool_input.top_k,
    )
