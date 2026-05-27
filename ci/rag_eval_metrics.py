from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RetrievedSource:
    chunk_id: UUID
    tenant_id: UUID
    text: str


def retrieval_hit_at_k(
    sources: list[RetrievedSource],
    expected_source_marker: str,
) -> bool:
    marker = expected_source_marker.casefold()
    return any(marker in source.text.casefold() for source in sources)


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
