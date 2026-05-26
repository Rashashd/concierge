from collections.abc import Awaitable, Callable, Sequence
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas import ChunkReference, RAGSearchOutput, ToolError


class RetrievedChunk(BaseModel):
    chunk_id: UUID
    content_item_id: UUID
    text: str = Field(..., min_length=1)
    score: float


type ChunkRetriever = Callable[
    [UUID, list[float], int],
    Awaitable[Sequence[RetrievedChunk]],
]


class RAGService:
    def __init__(
        self,
        embeddings_client: object | None,
        chunk_retriever: ChunkRetriever | None,
    ) -> None:
        self._embeddings_client = embeddings_client
        self._chunk_retriever = chunk_retriever

    async def search(
        self,
        tenant_id: UUID,
        query: str,
        top_k: int,
    ) -> RAGSearchOutput | ToolError:
        if self._embeddings_client is None or self._chunk_retriever is None:
            return ToolError(
                tool="rag_search",
                code="retrieval_unavailable",
                message="Tenant CMS retrieval is not wired yet.",
            )

        try:
            embedding = await self.embed_query(query)
            chunks = await self._chunk_retriever(tenant_id, embedding, top_k)
        except RuntimeError as exc:
            return ToolError(
                tool="rag_search",
                code="retrieval_failed",
                message=str(exc),
            )

        if not chunks:
            return ToolError(
                tool="rag_search",
                code="no_chunks_found",
                message="No tenant content matched the question.",
            )

        return RAGSearchOutput(
            answer=synthesize_answer(query=query, chunks=chunks),
            source_chunks=[
                ChunkReference(
                    chunk_id=chunk.chunk_id,
                    content_item_id=chunk.content_item_id,
                    text=chunk.text,
                    score=chunk.score,
                )
                for chunk in chunks
            ],
        )

    async def embed_query(self, query: str) -> list[float]:
        if self._embeddings_client is None:
            raise RuntimeError("Embedding client is not configured.")

        embed_query = getattr(self._embeddings_client, "aembed_query", None)
        if embed_query is None:
            raise RuntimeError(
                "Embedding client does not support async query embeddings."
            )

        embedding = await embed_query(query)
        return [float(value) for value in embedding]


def synthesize_answer(query: str, chunks: Sequence[RetrievedChunk]) -> str:
    joined = "\n\n".join(chunk.text for chunk in chunks[:3])
    return (
        "Based on this tenant's content, here is the most relevant information "
        f"for: {query}\n\n{joined}"
    )


def build_unwired_rag_service() -> RAGService:
    return RAGService(embeddings_client=None, chunk_retriever=None)
