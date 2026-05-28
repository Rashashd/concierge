"""CI gate for the Concierge intent classifier."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from sklearn.metrics import classification_report, f1_score


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_SERVER_DIR = REPO_ROOT / "model-server"
DATA_PATH = REPO_ROOT / "notebooks" / "data" / "processed" / "classifier_test.csv"
THRESHOLDS_PATH = REPO_ROOT / "ci" / "eval_thresholds.yaml"

sys.path.insert(0, str(MODEL_SERVER_DIR))

from app.inference import IntentClassifier  # noqa: E402


def _load_thresholds(path: Path) -> dict[str, Any]:
    """Load committed CI thresholds."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_eval() -> dict[str, Any]:
    """Evaluate the shipped classifier on the held-out test set."""
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Missing {DATA_PATH}. Extract concierge_classifier_artifacts.zip "
            "into the repo root before running classifier CI."
        )

    thresholds = _load_thresholds(THRESHOLDS_PATH)
    classifier_thresholds = thresholds.get("classifier", {})

    macro_f1_min = float(classifier_thresholds.get("macro_f1_min", 0.0))
    p95_latency_ms_max = float(classifier_thresholds.get("p95_latency_ms_max", 100.0))

    test_df = pd.read_csv(DATA_PATH)
    classifier = IntentClassifier()

    y_true = test_df["label"].astype(str).tolist()
    y_pred: list[str] = []
    latencies_ms: list[float] = []

    for text in test_df["text"].astype(str).tolist():
        started = time.perf_counter()
        prediction = classifier.predict(text)
        elapsed_ms = (time.perf_counter() - started) * 1000

        latencies_ms.append(elapsed_ms)
        y_pred.append(str(prediction["label"]))

    macro_f1 = f1_score(y_true, y_pred, average="macro")
    report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)

    latencies_sorted = sorted(latencies_ms)
    p95_index = max(0, int(len(latencies_sorted) * 0.95) - 1)
    p95_latency_ms = latencies_sorted[p95_index]

    failures: list[str] = []

    if macro_f1 < macro_f1_min:
        failures.append(
            f"macro_f1={macro_f1:.4f} is below threshold {macro_f1_min:.4f}"
        )

    if p95_latency_ms > p95_latency_ms_max:
        failures.append(
            f"p95_latency_ms={p95_latency_ms:.2f} exceeds threshold "
            f"{p95_latency_ms_max:.2f}"
        )

    return {
        "passed": not failures,
        "failures": failures,
        "model_version": classifier.model_version,
        "shipped_model": classifier.shipped_model,
        "macro_f1": macro_f1,
        "p95_latency_ms": p95_latency_ms,
        "thresholds": {
            "macro_f1_min": macro_f1_min,
            "p95_latency_ms_max": p95_latency_ms_max,
        },
        "classification_report": report,
    }


def main() -> int:
    """Run the classifier eval gate."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args()

    payload = run_eval()

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            f"classifier macro-F1={payload['macro_f1']:.4f} "
            f"p95={payload['p95_latency_ms']:.2f}ms "
            f"passed={payload['passed']}"
        )
        for failure in payload["failures"]:
            print(f"FAIL: {failure}")

    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
