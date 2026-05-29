import sys
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.append(str(REPO_ROOT / "ci" / "rag"))

from rag_eval_metrics import (  # noqa: E402
    RetrievedSource,
    answer_contains_expected,
    count_cross_tenant_leaks,
    expected_doc_mrr_at_k,
    expected_doc_precision_at_k,
    expected_source_rank,
    expected_source_rank_by_fixture,
    marker_precision_at_k,
    ratio,
    retrieval_hit_at_k,
    retrieval_hit_at_k_by_fixture,
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
    assert expected_source_rank(sources, "[alpha-hours]") == 2
    assert expected_source_rank(sources, "[missing]") is None


def test_marker_precision_at_k_scores_expected_context_density() -> None:
    tenant_id = uuid4()
    sources = [
        RetrievedSource(
            chunk_id=uuid4(),
            tenant_id=tenant_id,
            text="[alpha-hours] expected context",
        ),
        RetrievedSource(chunk_id=uuid4(), tenant_id=tenant_id, text="distractor"),
        RetrievedSource(
            chunk_id=uuid4(),
            tenant_id=tenant_id,
            text="[alpha-hours] second expected context",
        ),
        RetrievedSource(chunk_id=uuid4(), tenant_id=tenant_id, text="other"),
    ]

    assert marker_precision_at_k(sources, "[alpha-hours]") == 0.5
    assert marker_precision_at_k([], "[alpha-hours]") == 0.0


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


def test_retrieval_hit_by_fixture_detects_expected_path() -> None:
    tenant_id = uuid4()
    chunk_id_1 = uuid4()
    chunk_id_2 = uuid4()
    chunk_fixture_paths = {
        chunk_id_1: "alpha-hours.md",
        chunk_id_2: "alpha-cancel.md",
    }
    sources = [
        RetrievedSource(
            chunk_id=chunk_id_1,
            tenant_id=tenant_id,
            text="Alpha Clinic is open Monday to Friday.",
            fixture_path="alpha-hours.md",
        ),
        RetrievedSource(
            chunk_id=chunk_id_2,
            tenant_id=tenant_id,
            text="Cancel with 24 hours notice.",
            fixture_path="alpha-cancel.md",
        ),
    ]

    assert retrieval_hit_at_k_by_fixture(
        sources, ["alpha-hours.md"], chunk_fixture_paths
    )
    assert not retrieval_hit_at_k_by_fixture(
        sources, ["missing.md"], chunk_fixture_paths
    )
    assert (
        expected_source_rank_by_fixture(
            sources, ["alpha-hours.md"], chunk_fixture_paths
        )
        == 1
    )
    assert (
        expected_source_rank_by_fixture(
            sources, ["alpha-cancel.md"], chunk_fixture_paths
        )
        == 2
    )
    assert (
        expected_source_rank_by_fixture(sources, ["missing.md"], chunk_fixture_paths)
        is None
    )


def test_retrieval_hit_by_fixture_multi_hop() -> None:
    tenant_id = uuid4()
    chunk_id_1 = uuid4()
    chunk_id_2 = uuid4()
    chunk_id_3 = uuid4()
    chunk_fixture_paths = {
        chunk_id_1: "alpha-hours.md",
        chunk_id_2: "distractors/alpha-archived-operations.md",
        chunk_id_3: "alpha-cancel.md",
    }
    sources = [
        RetrievedSource(
            chunk_id=chunk_id_1,
            tenant_id=tenant_id,
            text="Alpha Clinic is open Monday to Friday.",
            fixture_path="alpha-hours.md",
        ),
        RetrievedSource(
            chunk_id=chunk_id_2,
            tenant_id=tenant_id,
            text="Archive content about scheduling.",
            fixture_path="distractors/alpha-archived-operations.md",
        ),
        RetrievedSource(
            chunk_id=chunk_id_3,
            tenant_id=tenant_id,
            text="Cancel with 24 hours notice.",
            fixture_path="alpha-cancel.md",
        ),
    ]

    assert retrieval_hit_at_k_by_fixture(
        sources,
        ["alpha-hours.md", "alpha-cancel.md"],
        chunk_fixture_paths,
    )
    assert (
        expected_source_rank_by_fixture(
            sources,
            ["alpha-hours.md", "alpha-cancel.md"],
            chunk_fixture_paths,
        )
        == 1
    )


def test_expected_doc_precision_at_k_single_hop() -> None:
    tenant_id = uuid4()
    chunk_ids = [uuid4() for _ in range(5)]
    chunk_fixture_paths = {
        chunk_ids[0]: "alpha-hours.md",
        chunk_ids[1]: "alpha-hours.md",
        chunk_ids[2]: "distractors/alpha-archived-operations.md",
        chunk_ids[3]: "alpha-hours.md",
        chunk_ids[4]: "distractors/alpha-draft-scheduling-policy.md",
    }
    fixture_names = [
        "alpha-hours.md",
        "alpha-hours.md",
        "distractors/alpha-archived-operations.md",
        "alpha-hours.md",
        "distractors/alpha-draft-scheduling-policy.md",
    ]
    sources = [
        RetrievedSource(
            chunk_id=cid,
            tenant_id=tenant_id,
            text=f"c{i}",
            fixture_path=fp,
        )
        for i, (cid, fp) in enumerate(zip(chunk_ids, fixture_names, strict=True))
    ]

    assert (
        expected_doc_precision_at_k(sources, chunk_fixture_paths, ["alpha-hours.md"])
        == 0.6
    )
    assert (
        expected_doc_precision_at_k([], chunk_fixture_paths, ["alpha-hours.md"]) == 0.0
    )


def test_expected_doc_precision_at_k_multi_hop() -> None:
    tenant_id = uuid4()
    chunk_ids = [uuid4() for _ in range(5)]
    chunk_fixture_paths = {
        chunk_ids[0]: "alpha-hours.md",
        chunk_ids[1]: "alpha-cancel.md",
        chunk_ids[2]: "distractors/alpha-archived-operations.md",
        chunk_ids[3]: "alpha-hours.md",
        chunk_ids[4]: "alpha-cancel.md",
    }
    fixture_names = [
        "alpha-hours.md",
        "alpha-cancel.md",
        "distractors/alpha-archived-operations.md",
        "alpha-hours.md",
        "alpha-cancel.md",
    ]
    sources = [
        RetrievedSource(
            chunk_id=cid,
            tenant_id=tenant_id,
            text=f"c{i}",
            fixture_path=fp,
        )
        for i, (cid, fp) in enumerate(zip(chunk_ids, fixture_names, strict=True))
    ]

    expected_paths = ["alpha-hours.md", "alpha-cancel.md"]
    precision = expected_doc_precision_at_k(
        sources, chunk_fixture_paths, expected_paths
    )
    assert precision == 0.8


def test_expected_doc_mrr_at_k_single_hop() -> None:
    tenant_id = uuid4()
    chunk_ids = [uuid4() for _ in range(3)]
    chunk_fixture_paths = {
        chunk_ids[0]: "distractors/alpha-archived-operations.md",
        chunk_ids[1]: "alpha-hours.md",
        chunk_ids[2]: "alpha-hours.md",
    }
    fixture_names = [
        "distractors/alpha-archived-operations.md",
        "alpha-hours.md",
        "alpha-hours.md",
    ]
    sources = [
        RetrievedSource(
            chunk_id=cid,
            tenant_id=tenant_id,
            text=f"c{i}",
            fixture_path=fp,
        )
        for i, (cid, fp) in enumerate(zip(chunk_ids, fixture_names, strict=True))
    ]

    mrr = expected_doc_mrr_at_k(sources, chunk_fixture_paths, ["alpha-hours.md"])
    assert mrr == 0.5


def test_expected_doc_mrr_at_k_multi_hop() -> None:
    tenant_id = uuid4()
    chunk_ids = [uuid4() for _ in range(5)]
    chunk_fixture_paths = {
        chunk_ids[0]: "alpha-hours.md",
        chunk_ids[1]: "distractors/alpha-archived-operations.md",
        chunk_ids[2]: "alpha-cancel.md",
        chunk_ids[3]: "alpha-hours.md",
        chunk_ids[4]: "alpha-cancel.md",
    }
    fixture_names = [
        "alpha-hours.md",
        "distractors/alpha-archived-operations.md",
        "alpha-cancel.md",
        "alpha-hours.md",
        "alpha-cancel.md",
    ]
    sources = [
        RetrievedSource(
            chunk_id=cid,
            tenant_id=tenant_id,
            text=f"c{i}",
            fixture_path=fp,
        )
        for i, (cid, fp) in enumerate(zip(chunk_ids, fixture_names, strict=True))
    ]

    mrr = expected_doc_mrr_at_k(
        sources,
        chunk_fixture_paths,
        ["alpha-hours.md", "alpha-cancel.md"],
    )
    expected_mrr = (1.0 / 1 + 1.0 / 3) / 2
    assert abs(mrr - expected_mrr) < 1e-9


def test_ratio_handles_zero_total() -> None:
    assert ratio(0, 0) == 0.0
    assert ratio(5, 0) == 0.0
    assert ratio(3, 10) == 0.3
