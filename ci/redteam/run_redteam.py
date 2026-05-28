"""CI gate for Concierge prompt-injection, cross-tenant, and redaction rails."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARDRAILS_DIR = REPO_ROOT / "guardrails"
PROBES_PATH = Path(__file__).with_name("redteam_probes.json")
THRESHOLDS_PATH = REPO_ROOT / "ci" / "eval_thresholds.yaml"

sys.path.insert(0, str(GUARDRAILS_DIR))

from app.policies import check_input_policy  # noqa: E402


def _load_json(path: Path) -> list[dict[str, Any]]:
    """Load red-team probes."""
    return json.loads(path.read_text(encoding="utf-8"))


def _load_thresholds(path: Path) -> dict[str, Any]:
    """Load committed CI thresholds."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_redteam() -> dict[str, Any]:
    """Run deterministic red-team probes."""
    probes = _load_json(PROBES_PATH)
    thresholds = _load_thresholds(THRESHOLDS_PATH)

    required_refusal_rate = float(
        thresholds.get("redteam", {}).get("required_refusal_rate", 1.0)
    )

    results: list[dict[str, Any]] = []
    must_refuse_total = 0
    must_refuse_passed = 0

    for probe in probes:
        result = check_input_policy(
            message=str(probe["message"]),
            tenant_config={"blocked_topics": ["refund abuse"]},
        )

        expected_decision = str(probe["expected_decision"])
        decision_passed = result.decision == expected_decision
        redaction_passed = True

        for forbidden in probe.get("must_not_contain", []):
            if result.safe_text and forbidden in result.safe_text:
                redaction_passed = False

        if expected_decision == "refuse":
            must_refuse_total += 1
            if decision_passed:
                must_refuse_passed += 1

        results.append(
            {
                "id": probe["id"],
                "category": probe["category"],
                "expected_decision": expected_decision,
                "actual_decision": result.decision,
                "triggered_rules": result.triggered_rules,
                "decision_passed": decision_passed,
                "redaction_passed": redaction_passed,
                "safe_text": result.safe_text,
            }
        )

    refusal_rate = must_refuse_passed / must_refuse_total if must_refuse_total else 1.0

    failures = [
        row
        for row in results
        if not row["decision_passed"] or not row["redaction_passed"]
    ]

    if refusal_rate < required_refusal_rate:
        failures.append(
            {
                "id": "aggregate_refusal_rate",
                "expected_decision": f">={required_refusal_rate}",
                "actual_decision": str(refusal_rate),
                "decision_passed": False,
                "redaction_passed": True,
            }
        )

    return {
        "passed": not failures,
        "required_refusal_rate": required_refusal_rate,
        "refusal_rate": refusal_rate,
        "failures": failures,
        "results": results,
    }


def main() -> int:
    """Run the red-team CI gate."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    payload = run_redteam()

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"redteam refusal_rate={payload['refusal_rate']:.4f} "
            f"passed={payload['passed']}"
        )
        for failure in payload["failures"]:
            print(f"FAIL: {failure}")

    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
