import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.append(str(REPO_ROOT / "ci" / "rag"))

from run_rag_golden import (  # noqa: E402
    EvalExampleResult,
    _fixture_path,
    _load_distractors,
    _load_examples,
    _select_ragas_examples,
    _skipped_ragas_scores,
    chunk_markdown,
)

MARKER_PATTERNS = [
    "[alpha-hours]",
    "[alpha-location]",
    "[alpha-insurance]",
    "[alpha-cancel]",
    "[alpha-telehealth]",
    "[beta-shipping]",
    "[beta-returns]",
    "[beta-sizing]",
    "[beta-warranty]",
    "[beta-pickup]",
    "[gamma-onboarding]",
    "[gamma-support]",
    "[gamma-data-export]",
    "[gamma-security]",
    "[gamma-integrations]",
    "[alpha-hours-archive]",
    "[beta-shipping-archive]",
    "[gamma-onboarding-archive]",
]


def test_chunk_markdown_avoids_empty_chunks() -> None:
    markdown = """
# Guide

Introductory context about the document and how visitors use it.

For routine care, Alpha Clinic keeps weekday hours Monday through Friday, 8 AM to 6 PM.

Additional context about parking, forms, and follow-up workflows.
""".strip()

    chunks = chunk_markdown(markdown, max_chars=120)

    assert chunks
    assert all(chunk.strip() for chunk in chunks)


def test_chunk_markdown_splits_long_markdown() -> None:
    markdown = "\n\n".join(
        [
            "# Long Fixture",
            "A" * 180,
            "B" * 220,
            "C" * 220,
            "D" * 180,
        ]
    )

    chunks = chunk_markdown(markdown, max_chars=260)

    assert len(chunks) >= 3
    assert all(len(chunk) <= 260 for chunk in chunks)


def test_every_example_fixture_exists() -> None:
    for example in _load_examples():
        fixture_path = _fixture_path(example)
        assert fixture_path.exists()


def test_no_marker_strings_in_answer_fixtures() -> None:
    examples = _load_examples()
    for example in examples:
        fixture_path = _fixture_path(example)
        fixture_text = fixture_path.read_text(encoding="utf-8")
        for marker in MARKER_PATTERNS:
            assert marker not in fixture_text, (
                f"Marker {marker} found in {fixture_path}"
            )


def test_no_marker_strings_in_distractor_fixtures() -> None:
    distractors = _load_distractors()
    for distractor in distractors:
        fixture_path = _fixture_path(distractor)
        fixture_text = fixture_path.read_text(encoding="utf-8")
        for marker in MARKER_PATTERNS:
            assert marker not in fixture_text, (
                f"Marker {marker} found in {fixture_path}"
            )


def test_every_distractor_fixture_exists() -> None:
    for distractor in _load_distractors():
        fixture_path = _fixture_path(distractor)
        assert fixture_path.exists()
        assert fixture_path.read_text(encoding="utf-8").strip()


def test_single_hop_expected_fixture_matching() -> None:
    examples = _load_examples()
    single_hop = [e for e in examples if len(e.expected_fixture_paths) == 1]
    assert len(single_hop) > 0
    for example in single_hop:
        assert example.fixture_path in example.expected_fixture_paths
        fixture_path = _fixture_path(example)
        assert fixture_path.exists()


def test_multi_hop_expected_fixture_matching() -> None:
    examples = _load_examples()
    multi_hop = [e for e in examples if len(e.expected_fixture_paths) > 1]
    assert len(multi_hop) == 5
    for example in multi_hop:
        for fp in example.expected_fixture_paths:
            full_path = Path(_fixture_path(example).parent) / fp
            assert full_path.exists(), (
                f"Multi-hop fixture {fp} not found for {example.id}"
            )


def test_expected_fixture_paths_are_valid_for_all_examples() -> None:
    examples = _load_examples()
    for example in examples:
        assert len(example.expected_fixture_paths) >= 1
        for fp in example.expected_fixture_paths:
            full_path = Path(_fixture_path(example).parent) / fp
            assert full_path.exists(), f"Expected fixture {fp} missing for {example.id}"


def test_distractor_count_per_tenant() -> None:
    distractors = _load_distractors()
    by_tenant: dict[str, list] = {}
    for d in distractors:
        by_tenant.setdefault(d.tenant_slug, []).append(d)
    for tenant_slug, items in by_tenant.items():
        assert len(items) >= 3, (
            f"Tenant {tenant_slug} has {len(items)} distractors, need >= 3"
        )


def test_golden_example_count() -> None:
    examples = _load_examples()
    assert len(examples) == 20


def test_distractor_manifest_valid() -> None:
    distractor_path = (
        Path(__file__).resolve().parents[3] / "ci" / "rag" / "rag_eval_distractors.json"
    )
    with distractor_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    assert len(raw) >= 15


def test_ragas_sample_prefers_multihop_and_covers_tenants() -> None:
    results = [
        _make_eval_result("alpha-hours", ["alpha-hours.md"]),
        _make_eval_result("beta-shipping", ["beta-shipping.md"]),
        _make_eval_result("gamma-support", ["gamma-support.md"]),
        _make_eval_result("alpha-hours-cancel", ["alpha-hours.md", "alpha-cancel.md"]),
        _make_eval_result(
            "beta-shipping-returns", ["beta-shipping.md", "beta-returns.md"]
        ),
        _make_eval_result(
            "gamma-onboarding-integrations",
            ["gamma-onboarding.md", "gamma-integrations.md"],
        ),
    ]

    sample = _select_ragas_examples(example_results=results, sample_size=3)
    sample_ids = {result.example_id for result in sample}

    assert len(sample) == 3
    assert "alpha-hours-cancel" in sample_ids
    assert "beta-shipping-returns" in sample_ids
    assert "gamma-onboarding-integrations" in sample_ids
    assert {sample_id.split("-", maxsplit=1)[0] for sample_id in sample_ids} == {
        "alpha",
        "beta",
        "gamma",
    }


def test_skipped_ragas_scores_are_explicit() -> None:
    scores = _skipped_ragas_scores()

    assert scores["ragas_skipped"] is True
    assert scores["faithfulness"] is None
    assert scores["answer_relevancy"] is None
    assert scores["context_precision"] is None
    assert scores["context_recall"] is None


def _make_eval_result(
    example_id: str,
    expected_fixture_paths: list[str],
) -> EvalExampleResult:
    return EvalExampleResult(
        example_id=example_id,
        question="question",
        chunk_count=1,
        retrieval_hit=True,
        retrieval_hit_at_1=True,
        expected_source_rank=1,
        expected_doc_precision_at_5=1.0,
        expected_doc_mrr_at_5=1.0,
        answer_contains_expected=True,
        cross_tenant_leak_count=0,
        answer="answer",
        retrieved_contexts=["context"],
        reference_answer="reference",
        expected_fixture_paths=expected_fixture_paths,
    )
