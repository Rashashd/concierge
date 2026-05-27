import sys
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.append(str(REPO_ROOT / "ci"))

from rag_eval_metrics import (  # noqa: E402
    RetrievedSource,
    answer_contains_expected,
    count_cross_tenant_leaks,
    retrieval_hit_at_k,
)


def test_retrieval_hit_at_k_detects_expected_marker() -> None:
    tenant_id = uuid4()
    sources = [
        RetrievedSource(chunk_id=uuid4(), tenant_id=tenant_id, text="unrelated"),
        RetrievedSource(
            chunk_id=uuid4(),
            tenant_id=tenant_id,
            text="[alpha-hours] Alpha Clinic is open Monday to Friday.",
        ),
    ]

    assert retrieval_hit_at_k(sources, "[alpha-hours]") is True
    assert retrieval_hit_at_k(sources, "[missing]") is False


def test_answer_contains_expected_requires_all_phrases() -> None:
    answer = "Alpha Clinic is open Monday through Friday from 8 AM to 6 PM."

    assert answer_contains_expected(answer, ["Monday through Friday", "8 AM"])
    assert not answer_contains_expected(answer, ["Monday through Friday", "Sunday"])


def test_count_cross_tenant_leaks() -> None:
    expected_tenant_id = uuid4()
    other_tenant_id = uuid4()
    sources = [
        RetrievedSource(
            chunk_id=uuid4(),
            tenant_id=expected_tenant_id,
            text="correct tenant",
        ),
        RetrievedSource(
            chunk_id=uuid4(),
            tenant_id=other_tenant_id,
            text="wrong tenant",
        ),
    ]

    assert count_cross_tenant_leaks(sources, expected_tenant_id) == 1
