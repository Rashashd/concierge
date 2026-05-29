"""Tenant-safe LLM-based reranker for pgvector retrieval candidates."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import structlog
from pydantic import BaseModel, Field
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from app.core.config import Settings

logger = structlog.get_logger(__name__)

RERANK_SYSTEM_PROMPT = """\
You are a reranker for a tenant CMS knowledge base. You receive retrieved \
document chunks and a user query. Your only job is to score each chunk by \
how relevant it is to answering the user's question.

Rules:
- Score ONLY the candidate indexes provided. Do not invent new indexes.
- Higher score means more relevant to the user question.
- Prefer chunks that directly answer the question over archived, draft, \
internal, holiday, legacy, or distractor documents.
- Do NOT answer the question. Only score relevance.
- Do NOT invent or modify chunk content.

Return ONLY a JSON object with a "decisions" array. Each decision has \
"index" (int) and "score" (float 0.0-1.0). Example:
{"decisions": [{"index": 0, "score": 0.9}, {"index": 1, "score": 0.3}]}

Do not include any other text, markdown fences, or explanations.
The output must be valid parseable JSON.\
"""

_JSON_PATTERN = re.compile(r"\{[\s\S]*\}")


class RerankCandidate(BaseModel):
    index: int = Field(..., ge=0)
    chunk_id: str
    text: str = Field(..., min_length=1)


class RerankDecision(BaseModel):
    index: int = Field(..., ge=0)
    score: float = Field(..., ge=0.0, le=1.0)


class Reranker:
    """Abstract reranker interface."""

    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankDecision]:
        raise NotImplementedError


class LLMReranker(Reranker):
    """Reranker that uses an LLM with JSON-mode scoring."""

    def __init__(self, llm: Any) -> None:
        self._llm = llm

    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankDecision]:
        candidates_text = "\n".join(f"Index {c.index}: {c.text}" for c in candidates)
        indexes_str = ", ".join(str(c.index) for c in candidates)
        user_prompt = (
            f"User query: {query}\n\n"
            f"Candidate chunks:\n{candidates_text}\n\n"
            f"Score each of these candidate indexes ({indexes_str}) "
            f"by relevance to the query. Return JSON only."
        )

        try:
            result = await self._llm.ainvoke(
                [
                    ("system", RERANK_SYSTEM_PROMPT),
                    ("human", user_prompt),
                ]
            )
            content = result.content if hasattr(result, "content") else str(result)
            decisions = _parse_llm_json(content, candidates)
        except Exception as exc:
            logger.warning("llm_reranker_failed", error_type=type(exc).__name__)
            return _fallback_decisions(candidates)

        return _validate_decisions(decisions, candidates)


class CohereReranker(Reranker):
    """Reranker backed by Cohere's hosted rerank API."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int,
        client: Any | None = None,
    ) -> None:
        if client is None:
            import cohere

            client = cohere.AsyncClientV2(api_key, timeout=timeout_seconds)
        self._client = client
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self.failure_count = 0

    async def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
    ) -> list[RerankDecision]:
        documents = [candidate.text for candidate in candidates]
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self._max_retries + 1),
                wait=wait_exponential(multiplier=1, min=1, max=4),
                reraise=True,
            ):
                with attempt:
                    result = await asyncio.wait_for(
                        self._client.rerank(
                            model=self._model,
                            query=query,
                            documents=documents,
                            top_n=len(documents),
                        ),
                        timeout=self._timeout_seconds,
                    )
        except Exception as exc:
            self.failure_count += 1
            logger.warning("cohere_reranker_failed", error_type=type(exc).__name__)
            return _fallback_decisions(candidates)

        decisions = [
            RerankDecision(
                index=candidates[item.index].index,
                score=float(item.relevance_score),
            )
            for item in result.results
            if 0 <= item.index < len(candidates)
        ]
        return _validate_decisions(decisions, candidates)


def build_reranker(*, settings: Settings, llm: object) -> Reranker:
    """Build the configured reranker implementation."""
    if settings.reranker_provider == "cohere":
        return CohereReranker(
            api_key=settings.cohere_api_key.get_secret_value(),
            model=settings.cohere_rerank_model,
            timeout_seconds=settings.reranker_timeout_seconds,
            max_retries=settings.reranker_max_retries,
        )
    return LLMReranker(llm=llm)


def _parse_llm_json(
    content: str,
    candidates: list[RerankCandidate],
) -> list[RerankDecision]:
    match = _JSON_PATTERN.search(content)
    if match is None:
        raise ValueError("No JSON found in reranker output")

    parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict) or "decisions" not in parsed:
        raise ValueError("Reranker output missing 'decisions' key")

    return [RerankDecision.model_validate(d) for d in parsed["decisions"]]


def _fallback_decisions(candidates: list[RerankCandidate]) -> list[RerankDecision]:
    return [RerankDecision(index=c.index, score=0.5) for c in candidates]


def _validate_decisions(
    decisions: list[RerankDecision],
    candidates: list[RerankCandidate],
) -> list[RerankDecision]:
    valid_indexes = {c.index for c in candidates}
    valid: list[RerankDecision] = []
    for decision in decisions:
        if decision.index not in valid_indexes:
            continue
        valid.append(decision)

    if not valid:
        return _fallback_decisions(candidates)

    seen: set[int] = set()
    unique: list[RerankDecision] = []
    for d in valid:
        if d.index not in seen:
            seen.add(d.index)
            unique.append(d)

    for c in candidates:
        if c.index not in seen:
            unique.append(RerankDecision(index=c.index, score=0.0))

    return unique
