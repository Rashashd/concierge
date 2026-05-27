from collections.abc import Awaitable, Callable, Sequence
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import chunks as chunk_repo
from app.schemas import ChunkReference, RAGSearchOutput, ToolError
from app.services.reranker import RerankCandidate, Reranker


class RetrievedChunk(BaseModel):
    chunk_id: UUID
    content_item_id: UUID
    text: str = Field(..., min_length=1)
    score: float


type ChunkRetriever = Callable[
    [UUID, list[float], int],
    Awaitable[Sequence[RetrievedChunk]],
]

_DEFAULT_RERANK_CANDIDATE_COUNT = 20


def _rerank_candidate_count(top_k: int) -> int:
    return min(max(top_k * 4, 12), 20)


class RAGService:
    def __init__(
        self,
        embeddings_client: object | None,
        chunk_retriever: ChunkRetriever | None,
        reranker: Reranker | None = None,
    ) -> None:
        self._embeddings_client = embeddings_client
        self._chunk_retriever = chunk_retriever
        self._reranker = reranker

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
            candidate_count = (
                _rerank_candidate_count(top_k)
                if self._reranker is not None
                else top_k
            )
            chunks = await self._chunk_retriever(
                tenant_id, embedding, candidate_count
            )
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

        if self._reranker is not None and len(chunks) > top_k:
            chunks = await self._rerank_and_truncate(
                query=query, chunks=chunks, top_k=top_k
            )
        else:
            chunks = chunks[:top_k]

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

    async def _rerank_and_truncate(
        self,
        query: str,
        chunks: Sequence[RetrievedChunk],
        top_k: int,
    ) -> Sequence[RetrievedChunk]:
        candidates = [
            RerankCandidate(
                index=i,
                chunk_id=str(chunk.chunk_id),
                text=chunk.text,
            )
            for i, chunk in enumerate(chunks)
        ]
        try:
            decisions = await self._reranker.rerank(
                query=query, candidates=candidates
            )
        except Exception:
            return chunks[:top_k]

        score_map = {d.index: d.score for d in decisions}
        indexed = list(enumerate(chunks))
        reranked = sorted(
            indexed,
            key=lambda pair: score_map.get(pair[0], 0.0),
            reverse=True,
        )
        return [chunk for _, chunk in reranked][:top_k]

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


def build_pgvector_rag_service(
    session: AsyncSession,
    embeddings_client: object,
    reranker: Reranker | None = None,
) -> RAGService:
    async def retrieve_chunks(
        tenant_id: UUID,
        embedding: list[float],
        top_k: int,
    ) -> Sequence[RetrievedChunk]:
        chunks = await chunk_repo.search_with_scores(
            session=session,
            tenant_id=tenant_id,
            query_embedding=embedding,
            k=top_k,
        )
        return [
            RetrievedChunk(
                chunk_id=chunk.id,
                content_item_id=chunk.content_item_id,
                text=chunk.text,
                score=score,
            )
            for chunk, score in chunks
        ]

    return RAGService(
        embeddings_client=embeddings_client,
        chunk_retriever=retrieve_chunks,
        reranker=reranker,
    )
