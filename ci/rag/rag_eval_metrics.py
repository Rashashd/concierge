from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RetrievedSource:
    chunk_id: UUID
    tenant_id: UUID
    text: str
    fixture_path: str | None = None


def retrieval_hit_at_k(
    sources: list[RetrievedSource],
    expected_source_marker: str,
) -> bool:
    return expected_source_rank(sources, expected_source_marker) is not None


def expected_source_rank(
    sources: list[RetrievedSource],
    expected_source_marker: str,
) -> int | None:
    marker = expected_source_marker.casefold()
    for index, source in enumerate(sources, start=1):
        if marker in source.text.casefold():
            return index
    return None


def marker_precision_at_k(
    sources: list[RetrievedSource],
    expected_source_marker: str,
) -> float:
    if not sources:
        return 0.0
    marker = expected_source_marker.casefold()
    matching = sum(1 for source in sources if marker in source.text.casefold())
    return matching / len(sources)


def retrieval_hit_at_k_by_fixture(
    sources: list[RetrievedSource],
    expected_fixture_paths: list[str],
    chunk_fixture_paths: dict[UUID, str],
) -> bool:
    return (
        expected_source_rank_by_fixture(
            sources, expected_fixture_paths, chunk_fixture_paths
        )
        is not None
    )


def expected_source_rank_by_fixture(
    sources: list[RetrievedSource],
    expected_fixture_paths: list[str],
    chunk_fixture_paths: dict[UUID, str],
) -> int | None:
    expected_set = set(expected_fixture_paths)
    for index, source in enumerate(sources, start=1):
        fp = chunk_fixture_paths.get(source.chunk_id)
        if fp is not None and fp in expected_set:
            return index
    return None


def expected_doc_precision_at_k(
    sources: list[RetrievedSource],
    chunk_fixture_paths: dict[UUID, str],
    expected_fixture_paths: list[str],
) -> float:
    if not sources:
        return 0.0
    expected_set = set(expected_fixture_paths)
    matching = sum(
        1
        for source in sources
        if chunk_fixture_paths.get(source.chunk_id) in expected_set
    )
    return matching / len(sources)


def expected_doc_mrr_at_k(
    sources: list[RetrievedSource],
    chunk_fixture_paths: dict[UUID, str],
    expected_fixture_paths: list[str],
) -> float:
    expected_set = set(expected_fixture_paths)
    seen: set[str] = set()
    reciprocal_rank_sum = 0.0
    for rank, source in enumerate(sources, start=1):
        fp = chunk_fixture_paths.get(source.chunk_id)
        if fp is not None and fp in expected_set and fp not in seen:
            reciprocal_rank_sum += 1.0 / rank
            seen.add(fp)
    if not expected_set:
        return 0.0
    return reciprocal_rank_sum / len(expected_set)


def answer_contains_expected(answer: str, expected_phrases: list[str]) -> bool:
    answer_text = answer.casefold()
    return all(phrase.casefold() in answer_text for phrase in expected_phrases)


def count_cross_tenant_leaks(
    sources: list[RetrievedSource],
    expected_tenant_id: UUID,
) -> int:
    return sum(1 for source in sources if source.tenant_id != expected_tenant_id)


def ratio(passed: int, total: int) -> float:
    if total == 0:
        return 0.0
    return passed / total
