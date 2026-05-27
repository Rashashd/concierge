from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from datasets import Dataset
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from rag_eval_metrics import (
    RetrievedSource,
    answer_contains_expected,
    count_cross_tenant_leaks,
    ratio,
    retrieval_hit_at_k,
)
from ragas import evaluate
from ragas.metrics import Faithfulness, ResponseRelevancy
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.models import Chunk, ContentItem, Tenant
from app.infra.llm import get_embeddings, get_llm
from app.infra.vault import VaultClient, create_vault_client
from app.schemas import RAGSearchOutput
from app.services.rag import build_pgvector_rag_service

GOLDEN_PATH = Path(__file__).with_name("rag_golden.json")


class EvalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        extra="ignore",
    )

    vault_addr: str
    vault_token: SecretStr
    rag_eval_database_url: str


class GoldenExample(BaseModel):
    id: str
    tenant_slug: str
    tenant_name: str
    question: str
    content_title: str
    content: str
    expected_source_marker: str
    reference_answer: str
    expected_answer_phrases: list[str] = Field(min_length=1)


@dataclass(frozen=True)
class EvalExampleResult:
    example_id: str
    question: str
    retrieval_hit: bool
    answer_contains_expected: bool
    cross_tenant_leak_count: int
    answer: str
    retrieved_contexts: list[str]
    reference_answer: str


async def main() -> None:
    settings = EvalSettings()
    vault = create_vault_client(
        addr=settings.vault_addr,
        token=settings.vault_token.get_secret_value(),
    )
    app_settings = _build_app_settings(vault, settings)
    examples = _load_examples()

    embeddings = get_embeddings(app_settings)
    llm = get_llm(app_settings)

    engine = create_async_engine(settings.rag_eval_database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        chunk_tenants = await _seed_golden_data(
            session_factory=session_factory,
            examples=examples,
            embeddings=embeddings,
        )
        example_results = await _run_rag_examples(
            session_factory=session_factory,
            examples=examples,
            embeddings=embeddings,
            chunk_tenants=chunk_tenants,
        )
    finally:
        await engine.dispose()

    ragas_scores = _run_required_ragas(example_results, llm=llm, embeddings=embeddings)
    report = _build_report(example_results=example_results, ragas_scores=ragas_scores)
    print(json.dumps(report, indent=2, sort_keys=True))


def _build_app_settings(
    vault: VaultClient,
    eval_settings: EvalSettings,
) -> Settings:
    app_settings = Settings(
        vault_addr=eval_settings.vault_addr,
        vault_token=eval_settings.vault_token,
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
    app_settings.azure_openai_deployment = llm_config.get(
        "azure_openai_deployment", ""
    )
    app_settings.azure_openai_embedding_deployment = llm_config.get(
        "azure_openai_embedding_deployment", ""
    )
    app_settings.groq_api_key = SecretStr(llm_config.get("groq_api_key", ""))
    return app_settings


def _load_examples() -> list[GoldenExample]:
    with GOLDEN_PATH.open("r", encoding="utf-8") as file:
        raw_examples = json.load(file)
    return [GoldenExample.model_validate(example) for example in raw_examples]


async def _embed_documents(embeddings: Any, texts: list[str]) -> list[list[float]]:
    embed_documents = getattr(embeddings, "aembed_documents", None)
    if embed_documents is None:
        raise RuntimeError("Embedding client does not support async document embeds.")
    raw_embeddings = await embed_documents(texts)
    return [[float(value) for value in embedding] for embedding in raw_embeddings]


async def _seed_golden_data(
    session_factory: async_sessionmaker[Any],
    examples: list[GoldenExample],
    embeddings: Any,
) -> dict[UUID, UUID]:
    chunk_tenants: dict[UUID, UUID] = {}
    examples_by_tenant: dict[str, list[GoldenExample]] = {}
    for example in examples:
        examples_by_tenant.setdefault(example.tenant_slug, []).append(example)

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
                await session.execute(delete(Chunk).where(Chunk.tenant_id == tenant.id))
                await session.execute(
                    delete(ContentItem).where(ContentItem.tenant_id == tenant.id)
                )

                texts = [example.content for example in tenant_examples]
                embeddings_for_texts = await _embed_documents(embeddings, texts)
                for example, embedding in zip(
                    tenant_examples, embeddings_for_texts, strict=True
                ):
                    content_item = ContentItem(
                        tenant_id=tenant.id,
                        title=example.content_title,
                        body=example.content,
                        content_type="rag_eval",
                    )
                    session.add(content_item)
                    await session.flush()
                    chunk = Chunk(
                        tenant_id=tenant.id,
                        content_item_id=content_item.id,
                        chunk_index=0,
                        text=example.content,
                        embedding=embedding,
                        chunk_metadata={"rag_eval_id": example.id},
                    )
                    session.add(chunk)
                    await session.flush()
                    chunk_tenants[chunk.id] = tenant.id

    return chunk_tenants


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
    chunk_tenants: dict[UUID, UUID],
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
                    )
                    for source in rag_output.source_chunks
                ]
                results.append(
                    EvalExampleResult(
                        example_id=example.id,
                        question=example.question,
                        retrieval_hit=retrieval_hit_at_k(
                            sources=sources,
                            expected_source_marker=example.expected_source_marker,
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
                    )
                )
    return results


async def _tenant_id_for_slug(session: Any, slug: str) -> UUID:
    result = await session.execute(select(Tenant.id).where(Tenant.slug == slug))
    tenant_id = result.scalar_one_or_none()
    if tenant_id is None:
        raise RuntimeError(f"Eval tenant not found: {slug}")
    return tenant_id


def _run_required_ragas(
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
        metrics=[Faithfulness(), ResponseRelevancy()],
        llm=llm,
        embeddings=embeddings,
        raise_exceptions=True,
        show_progress=False,
    )
    frame = evaluation.to_pandas()
    return {
        "faithfulness": float(frame["faithfulness"].mean()),
        "answer_relevancy": float(frame["answer_relevancy"].mean()),
    }


def _build_report(
    example_results: list[EvalExampleResult],
    ragas_scores: dict[str, float],
) -> dict[str, Any]:
    total = len(example_results)
    retrieval_hits = sum(result.retrieval_hit for result in example_results)
    answer_hits = sum(result.answer_contains_expected for result in example_results)
    leak_count = sum(result.cross_tenant_leak_count for result in example_results)
    return {
        "example_count": total,
        "retrieval_hit_at_5": ratio(retrieval_hits, total),
        "answer_contains_expected": ratio(answer_hits, total),
        "cross_tenant_leak_count": leak_count,
        **ragas_scores,
        "examples": [
            {
                "id": result.example_id,
                "retrieval_hit": result.retrieval_hit,
                "answer_contains_expected": result.answer_contains_expected,
                "cross_tenant_leak_count": result.cross_tenant_leak_count,
            }
            for result in example_results
        ],
    }


if __name__ == "__main__":
    asyncio.run(main())
