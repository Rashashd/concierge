# ruff: noqa: E402
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from datasets import Dataset
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from rag_eval_metrics import (
    RetrievedSource,
    answer_contains_expected,
    count_cross_tenant_leaks,
    expected_doc_mrr_at_k,
    expected_doc_precision_at_k,
    expected_source_rank_by_fixture,
    ratio,
    retrieval_hit_at_k_by_fixture,
)
from ragas import evaluate
from ragas.metrics import (
    Faithfulness,
    LLMContextPrecisionWithReference,
    LLMContextRecall,
    ResponseRelevancy,
)
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.models import Tenant
from app.infra.llm import get_embeddings, get_llm
from app.infra.vault import VaultClient, create_vault_client
from app.repositories import chunks as chunk_repo
from app.repositories import content as content_repo
from app.schemas import RAGSearchOutput
from app.services.rag import build_pgvector_rag_service
from app.services.reranker import Reranker, build_reranker

GOLDEN_PATH = Path(__file__).with_name("rag_golden.json")
DISTRACTOR_PATH = Path(__file__).with_name("rag_eval_distractors.json")
FIXTURE_ROOT = Path(__file__).with_name("rag_eval_docs")
TEMP_CONTENT_TYPE = "rag_eval_temp_ci"
DEFAULT_CHUNK_MAX_CHARS = 300
DEFAULT_RAGAS_TIMEOUT_SECONDS = 180


class EvalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        extra="ignore",
    )

    vault_addr: str
    vault_token: SecretStr
    rag_eval_database_url: str
    ragas_timeout_seconds: int = DEFAULT_RAGAS_TIMEOUT_SECONDS


class GoldenExample(BaseModel):
    id: str
    tenant_slug: str
    tenant_name: str
    question: str
    content_title: str
    fixture_path: str = Field(min_length=1)
    expected_fixture_paths: list[str] = Field(min_length=1)
    reference_answer: str
    expected_answer_phrases: list[str] = Field(min_length=1)


class DistractorFixture(BaseModel):
    tenant_slug: str
    content_title: str
    fixture_path: str = Field(min_length=1)


@dataclass(frozen=True)
class SeededEvalData:
    chunk_tenants: dict[UUID, UUID]
    chunk_fixture_paths: dict[UUID, str]
    chunk_counts: dict[str, int]
    distractor_chunk_count: int


@dataclass(frozen=True)
class EvalExampleResult:
    example_id: str
    question: str
    chunk_count: int
    retrieval_hit: bool
    retrieval_hit_at_1: bool
    expected_source_rank: int | None
    expected_doc_precision_at_5: float
    expected_doc_mrr_at_5: float
    answer_contains_expected: bool
    cross_tenant_leak_count: int
    answer: str
    retrieved_contexts: list[str]
    reference_answer: str
    expected_fixture_paths: list[str]


async def main() -> None:
    settings = EvalSettings()
    vault = create_vault_client(
        addr=settings.vault_addr,
        token=settings.vault_token.get_secret_value(),
    )
    app_settings = _build_app_settings(vault, settings)
    examples = _load_examples()
    distractors = _load_distractors()

    embeddings = get_embeddings(app_settings)
    llm = get_llm(app_settings)
    reranker = build_reranker(settings=app_settings, llm=llm)

    engine = create_async_engine(settings.rag_eval_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        seeded_data = await _seed_golden_data(
            session_factory=session_factory,
            examples=examples,
            distractors=distractors,
            embeddings=embeddings,
        )
        example_results = await _run_rag_examples(
            session_factory=session_factory,
            examples=examples,
            embeddings=embeddings,
            reranker=reranker,
            app_settings=app_settings,
            chunk_tenants=seeded_data.chunk_tenants,
            chunk_fixture_paths=seeded_data.chunk_fixture_paths,
            chunk_counts=seeded_data.chunk_counts,
        )
    finally:
        await engine.dispose()

    reranker_failure_count = int(getattr(reranker, "failure_count", 0))
    if app_settings.reranker_provider == "cohere" and reranker_failure_count:
        raise RuntimeError(
            "Cohere reranker failed during eval; refusing to report fallback "
            f"metrics as Cohere results. failures={reranker_failure_count}"
        )

    ragas_scores = await _run_required_ragas(
        example_results,
        llm=llm,
        embeddings=embeddings,
        timeout_seconds=settings.ragas_timeout_seconds,
    )
    report = _build_report(
        example_results=example_results,
        ragas_scores=ragas_scores,
        distractor_chunk_count=seeded_data.distractor_chunk_count,
        retrieval_mode=app_settings.rag_retrieval_mode,
    )
    print(json.dumps(report, indent=2, sort_keys=True))


def _build_app_settings(
    vault: VaultClient,
    eval_settings: EvalSettings,
) -> Settings:
    app_settings = Settings(
        vault_addr=eval_settings.vault_addr,
        vault_token=eval_settings.vault_token,
        dev_widget_tenant_id=None,
    )
    llm_config = vault.get_llm_config()
    provider = llm_config.get("provider", app_settings.llm_provider)
    if provider not in ("openai", "azure", "groq"):
        raise RuntimeError(f"Unsupported LLM provider for RAG eval: {provider}")

    app_settings.database_url = eval_settings.rag_eval_database_url
    app_settings.llm_provider = provider  # type: ignore[assignment]
    app_settings.openai_api_key = SecretStr(llm_config.get("openai_api_key", ""))
    app_settings.openai_model = llm_config.get("openai_model", "gpt-4o-mini")
    app_settings.openai_embedding_model = llm_config.get(
        "openai_embedding_model", "text-embedding-3-small"
    )
    app_settings.azure_openai_api_key = SecretStr(
        llm_config.get("azure_openai_api_key", "")
    )
    app_settings.azure_openai_endpoint = llm_config.get("azure_openai_endpoint", "")
    app_settings.azure_openai_deployment = llm_config.get("azure_openai_deployment", "")
    app_settings.azure_openai_embedding_deployment = llm_config.get(
        "azure_openai_embedding_deployment", ""
    )
    app_settings.groq_api_key = SecretStr(llm_config.get("groq_api_key", ""))
    app_settings.reranker_provider = llm_config.get(
        "reranker_provider", app_settings.reranker_provider
    )  # type: ignore[assignment]
    app_settings.cohere_api_key = SecretStr(llm_config.get("cohere_api_key", ""))
    app_settings.cohere_rerank_model = llm_config.get(
        "cohere_rerank_model", app_settings.cohere_rerank_model
    )
    app_settings.reranker_timeout_seconds = float(
        llm_config.get(
            "reranker_timeout_seconds",
            str(app_settings.reranker_timeout_seconds),
        )
    )
    app_settings.reranker_max_retries = int(
        llm_config.get(
            "reranker_max_retries",
            str(app_settings.reranker_max_retries),
        )
    )
    app_settings.rag_retrieval_mode = llm_config.get(
        "rag_retrieval_mode", app_settings.rag_retrieval_mode
    )  # type: ignore[assignment]
    app_settings.hybrid_vector_weight = float(
        llm_config.get("hybrid_vector_weight", str(app_settings.hybrid_vector_weight))
    )
    app_settings.hybrid_keyword_weight = float(
        llm_config.get("hybrid_keyword_weight", str(app_settings.hybrid_keyword_weight))
    )
    app_settings.hybrid_vector_candidate_count = int(
        llm_config.get(
            "hybrid_vector_candidate_count",
            str(app_settings.hybrid_vector_candidate_count),
        )
    )
    app_settings.hybrid_keyword_candidate_count = int(
        llm_config.get(
            "hybrid_keyword_candidate_count",
            str(app_settings.hybrid_keyword_candidate_count),
        )
    )
    return app_settings


def _load_examples() -> list[GoldenExample]:
    with GOLDEN_PATH.open("r", encoding="utf-8") as file:
        raw_examples = json.load(file)
    return [GoldenExample.model_validate(example) for example in raw_examples]


def _load_distractors() -> list[DistractorFixture]:
    with DISTRACTOR_PATH.open("r", encoding="utf-8") as file:
        raw_distractors = json.load(file)
    return [DistractorFixture.model_validate(item) for item in raw_distractors]


def _fixture_path(fixture: GoldenExample | DistractorFixture) -> Path:
    return FIXTURE_ROOT / fixture.fixture_path


def _load_fixture_markdown(fixture: GoldenExample | DistractorFixture) -> str:
    fixture_path = _fixture_path(fixture)
    if not fixture_path.exists():
        raise FileNotFoundError(f"Missing eval fixture: {fixture_path}")
    return fixture_path.read_text(encoding="utf-8").strip()


def chunk_markdown(
    markdown: str,
    *,
    max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
) -> list[str]:
    sections = [
        section.strip() for section in markdown.split("\n\n") if section.strip()
    ]
    chunks: list[str] = []
    current = ""

    for section in sections:
        section_chunks = _split_oversized_section(section, max_chars=max_chars)
        for piece in section_chunks:
            if not current:
                current = piece
                continue

            candidate = f"{current}\n\n{piece}"
            if len(candidate) <= max_chars:
                current = candidate
                continue

            chunks.append(current)
            current = piece

    if current:
        chunks.append(current)

    return [chunk for chunk in chunks if chunk.strip()]


def _split_oversized_section(section: str, *, max_chars: int) -> list[str]:
    if len(section) <= max_chars:
        return [section]

    words = section.split()
    parts: list[str] = []
    current_words: list[str] = []
    current_length = 0
    for word in words:
        word_length = len(word) + (1 if current_words else 0)
        if current_words and current_length + word_length > max_chars:
            parts.append(" ".join(current_words))
            current_words = [word]
            current_length = len(word)
            continue
        current_words.append(word)
        current_length += word_length

    if current_words:
        parts.append(" ".join(current_words))
    return parts


async def _embed_documents(embeddings: Any, texts: list[str]) -> list[list[float]]:
    embed_documents = getattr(embeddings, "aembed_documents", None)
    if embed_documents is None:
        raise RuntimeError("Embedding client does not support async document embeds.")
    raw_embeddings = await embed_documents(texts)
    return [[float(value) for value in embedding] for embedding in raw_embeddings]


async def _seed_golden_data(
    session_factory: async_sessionmaker[Any],
    examples: list[GoldenExample],
    distractors: list[DistractorFixture],
    embeddings: Any,
) -> SeededEvalData:
    chunk_tenants: dict[UUID, UUID] = {}
    chunk_fixture_paths: dict[UUID, str] = {}
    chunk_counts: dict[str, int] = {}
    distractor_chunk_count = 0
    examples_by_tenant: dict[str, list[GoldenExample]] = {}
    for example in examples:
        examples_by_tenant.setdefault(example.tenant_slug, []).append(example)
    distractors_by_tenant: dict[str, list[DistractorFixture]] = {}
    for distractor in distractors:
        distractors_by_tenant.setdefault(distractor.tenant_slug, []).append(distractor)

    for tenant_slug, tenant_examples in examples_by_tenant.items():
        tenant_name = tenant_examples[0].tenant_name
        async with session_factory() as session:
            async with session.begin():
                tenant = await _get_or_create_tenant(
                    session=session,
                    slug=tenant_slug,
                    name=tenant_name,
                )
                await session.execute(
                    text("SELECT set_config('app.tenant_id', :tid, true)"),
                    {"tid": str(tenant.id)},
                )
                await chunk_repo.delete_by_tenant(session, tenant.id)
                await content_repo.delete_by_tenant(session, tenant.id)

                for example in tenant_examples:
                    chunk_ids = await _ingest_eval_fixture(
                        session=session,
                        tenant_id=tenant.id,
                        title=example.content_title,
                        fixture_path=example.fixture_path,
                        embeddings=embeddings,
                        metadata={"rag_eval_id": example.id},
                    )
                    chunk_counts[example.id] = len(chunk_ids)
                    for chunk_id in chunk_ids:
                        chunk_tenants[chunk_id] = tenant.id
                        chunk_fixture_paths[chunk_id] = example.fixture_path

                for distractor in distractors_by_tenant.get(tenant_slug, []):
                    chunk_ids = await _ingest_eval_fixture(
                        session=session,
                        tenant_id=tenant.id,
                        title=distractor.content_title,
                        fixture_path=distractor.fixture_path,
                        embeddings=embeddings,
                        metadata={"rag_eval_distractor": True},
                    )
                    distractor_chunk_count += len(chunk_ids)
                    for chunk_id in chunk_ids:
                        chunk_tenants[chunk_id] = tenant.id
                        chunk_fixture_paths[chunk_id] = distractor.fixture_path

    return SeededEvalData(
        chunk_tenants=chunk_tenants,
        chunk_fixture_paths=chunk_fixture_paths,
        chunk_counts=chunk_counts,
        distractor_chunk_count=distractor_chunk_count,
    )


async def _ingest_eval_fixture(
    *,
    session: Any,
    tenant_id: UUID,
    title: str,
    fixture_path: str,
    embeddings: Any,
    metadata: dict[str, Any],
) -> list[UUID]:
    markdown = _load_fixture_text(fixture_path)
    texts = chunk_markdown(markdown)
    embeddings_for_texts = await _embed_documents(embeddings, texts)
    content_item = await content_repo.create(
        session,
        tenant_id=tenant_id,
        title=title,
        body=markdown,
        content_type=TEMP_CONTENT_TYPE,
    )
    chunk_rows = await chunk_repo.create_bulk(
        session,
        tenant_id=tenant_id,
        content_item_id=content_item.id,
        texts=texts,
        embeddings=embeddings_for_texts,
        metadatas=[
            {
                **metadata,
                "fixture_path": fixture_path,
            }
            for _ in texts
        ],
    )
    return [chunk.id for chunk in chunk_rows]


def _load_fixture_text(fixture_path: str) -> str:
    path = FIXTURE_ROOT / fixture_path
    if not path.exists():
        raise FileNotFoundError(f"Missing eval fixture: {path}")
    return path.read_text(encoding="utf-8").strip()


async def _get_or_create_tenant(
    session: Any,
    slug: str,
    name: str,
) -> Tenant:
    result = await session.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if tenant is not None:
        return tenant

    tenant = Tenant(name=name, slug=slug)
    session.add(tenant)
    await session.flush()
    return tenant


async def _run_rag_examples(
    session_factory: async_sessionmaker[Any],
    examples: list[GoldenExample],
    embeddings: Any,
    reranker: Reranker,
    app_settings: Settings,
    chunk_tenants: dict[UUID, UUID],
    chunk_fixture_paths: dict[UUID, str],
    chunk_counts: dict[str, int],
) -> list[EvalExampleResult]:
    results: list[EvalExampleResult] = []
    for example in examples:
        async with session_factory() as session:
            async with session.begin():
                tenant_id = await _tenant_id_for_slug(session, example.tenant_slug)
                await session.execute(
                    text("SELECT set_config('app.tenant_id', :tid, true)"),
                    {"tid": str(tenant_id)},
                )
                rag_service = build_pgvector_rag_service(
                    session=session,
                    embeddings_client=embeddings,
                    reranker=reranker,
                    retrieval_mode=app_settings.rag_retrieval_mode,
                    hybrid_vector_weight=app_settings.hybrid_vector_weight,
                    hybrid_keyword_weight=app_settings.hybrid_keyword_weight,
                    hybrid_vector_candidate_count=app_settings.hybrid_vector_candidate_count,
                    hybrid_keyword_candidate_count=app_settings.hybrid_keyword_candidate_count,
                )
                rag_output = await rag_service.search(
                    tenant_id=tenant_id,
                    query=example.question,
                    top_k=5,
                )
                if not isinstance(rag_output, RAGSearchOutput):
                    raise RuntimeError(
                        f"RAG failed for {example.id}: "
                        f"{rag_output.code} {rag_output.message}"
                    )

                sources = [
                    RetrievedSource(
                        chunk_id=source.chunk_id,
                        tenant_id=chunk_tenants[source.chunk_id],
                        text=source.text,
                        fixture_path=chunk_fixture_paths.get(source.chunk_id),
                    )
                    for source in rag_output.source_chunks
                ]
                source_rank = expected_source_rank_by_fixture(
                    sources=sources,
                    expected_fixture_paths=example.expected_fixture_paths,
                    chunk_fixture_paths=chunk_fixture_paths,
                )
                results.append(
                    EvalExampleResult(
                        example_id=example.id,
                        question=example.question,
                        chunk_count=chunk_counts[example.id],
                        retrieval_hit=retrieval_hit_at_k_by_fixture(
                            sources=sources,
                            expected_fixture_paths=example.expected_fixture_paths,
                            chunk_fixture_paths=chunk_fixture_paths,
                        ),
                        retrieval_hit_at_1=source_rank == 1,
                        expected_source_rank=source_rank,
                        expected_doc_precision_at_5=expected_doc_precision_at_k(
                            sources=sources,
                            chunk_fixture_paths=chunk_fixture_paths,
                            expected_fixture_paths=example.expected_fixture_paths,
                        ),
                        expected_doc_mrr_at_5=expected_doc_mrr_at_k(
                            sources=sources,
                            chunk_fixture_paths=chunk_fixture_paths,
                            expected_fixture_paths=example.expected_fixture_paths,
                        ),
                        answer_contains_expected=answer_contains_expected(
                            answer=rag_output.answer,
                            expected_phrases=example.expected_answer_phrases,
                        ),
                        cross_tenant_leak_count=count_cross_tenant_leaks(
                            sources=sources,
                            expected_tenant_id=tenant_id,
                        ),
                        answer=rag_output.answer,
                        retrieved_contexts=[source.text for source in sources],
                        reference_answer=example.reference_answer,
                        expected_fixture_paths=example.expected_fixture_paths,
                    )
                )
    return results


async def _tenant_id_for_slug(session: Any, slug: str) -> UUID:
    result = await session.execute(select(Tenant.id).where(Tenant.slug == slug))
    tenant_id = result.scalar_one_or_none()
    if tenant_id is None:
        raise RuntimeError(f"Eval tenant not found: {slug}")
    return tenant_id


async def _run_required_ragas(
    example_results: list[EvalExampleResult],
    *,
    llm: Any,
    embeddings: Any,
    timeout_seconds: int,
) -> dict[str, float]:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                _evaluate_ragas_sync,
                example_results,
                llm,
                embeddings,
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError as exc:
        raise RuntimeError(
            f"RAGAS did not finish within {timeout_seconds} seconds."
        ) from exc


def _evaluate_ragas_sync(
    example_results: list[EvalExampleResult],
    llm: Any,
    embeddings: Any,
) -> dict[str, float]:
    dataset = Dataset.from_list(
        [
            {
                "user_input": result.question,
                "response": result.answer,
                "retrieved_contexts": result.retrieved_contexts,
                "reference": result.reference_answer,
            }
            for result in example_results
        ]
    )
    evaluation = evaluate(
        dataset,
        metrics=[
            Faithfulness(),
            ResponseRelevancy(),
            LLMContextPrecisionWithReference(),
            LLMContextRecall(),
        ],
        llm=llm,
        embeddings=embeddings,
        raise_exceptions=True,
        show_progress=False,
    )
    frame = evaluation.to_pandas()
    return {
        "faithfulness": float(frame["faithfulness"].mean()),
        "answer_relevancy": float(frame["answer_relevancy"].mean()),
        "context_precision": float(
            frame["llm_context_precision_with_reference"].mean()
        ),
        "context_recall": float(frame["context_recall"].mean()),
    }


def _build_report(
    example_results: list[EvalExampleResult],
    ragas_scores: dict[str, float],
    distractor_chunk_count: int,
    retrieval_mode: str,
) -> dict[str, Any]:
    total = len(example_results)
    retrieval_hits = sum(result.retrieval_hit for result in example_results)
    retrieval_hits_at_1 = sum(result.retrieval_hit_at_1 for result in example_results)
    answer_hits = sum(result.answer_contains_expected for result in example_results)
    leak_count = sum(result.cross_tenant_leak_count for result in example_results)
    answer_doc_chunks = sum(result.chunk_count for result in example_results)
    total_chunks = answer_doc_chunks + distractor_chunk_count
    reciprocal_rank_total = sum(
        1 / result.expected_source_rank
        for result in example_results
        if result.expected_source_rank is not None
    )
    ranked_results = [
        result.expected_source_rank
        for result in example_results
        if result.expected_source_rank is not None
    ]
    mean_expected_source_rank = (
        sum(ranked_results) / len(ranked_results) if ranked_results else 0.0
    )
    expected_doc_precision_total = sum(
        result.expected_doc_precision_at_5 for result in example_results
    )
    expected_doc_mrr_total = sum(
        result.expected_doc_mrr_at_5 for result in example_results
    )
    return {
        "baseline_type": "temporary_ci_ingestion",
        "retrieval_mode": retrieval_mode,
        "example_count": total,
        "chunk_count_total": total_chunks,
        "answer_doc_chunk_count": answer_doc_chunks,
        "distractor_chunk_count": distractor_chunk_count,
        "retrieval_hit_at_5": ratio(retrieval_hits, total),
        "retrieval_hit_at_1": ratio(retrieval_hits_at_1, total),
        "mrr_at_5": ratio(reciprocal_rank_total, total),
        "mean_expected_source_rank": mean_expected_source_rank,
        "expected_doc_precision_at_5": ratio(expected_doc_precision_total, total),
        "expected_doc_mrr_at_5": ratio(expected_doc_mrr_total, total),
        "answer_contains_expected": ratio(answer_hits, total),
        "cross_tenant_leak_count": leak_count,
        **ragas_scores,
        "examples": [
            {
                "id": result.example_id,
                "chunk_count": result.chunk_count,
                "retrieval_hit": result.retrieval_hit,
                "retrieval_hit_at_1": result.retrieval_hit_at_1,
                "expected_source_rank": result.expected_source_rank,
                "expected_doc_precision_at_5": result.expected_doc_precision_at_5,
                "expected_doc_mrr_at_5": result.expected_doc_mrr_at_5,
                "answer_contains_expected": result.answer_contains_expected,
                "cross_tenant_leak_count": result.cross_tenant_leak_count,
                "expected_fixture_paths": result.expected_fixture_paths,
            }
            for result in example_results
        ],
    }


if __name__ == "__main__":
    asyncio.run(main())
