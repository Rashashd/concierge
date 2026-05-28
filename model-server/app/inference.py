from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import onnxruntime as ort

ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts"
METADATA_PATH = ARTIFACT_DIR / "classifier_metadata.json"


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exp_values = np.exp(shifted)
    return exp_values / np.sum(exp_values, axis=1, keepdims=True)


class IntentClassifier:
    """Lean inference wrapper for the Concierge intent classifier."""

    def __init__(self) -> None:
        self.metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        self.labels = self.metadata["labels"]
        self.model_version = self.metadata["model_version"]
        self.confidence_threshold = self.metadata["confidence_threshold"]
        self.shipped_model = self.metadata["shipped_model"]

        if self.shipped_model == "classical":
            self.model = joblib.load(ARTIFACT_DIR / "classifier.joblib")
            self.vectorizer = None
            self.onnx_session = None
        elif self.shipped_model == "dl_onnx":
            self.model = None
            self.vectorizer = joblib.load(ARTIFACT_DIR / "dl_vectorizer.joblib")
            self.onnx_session = ort.InferenceSession(
                str(ARTIFACT_DIR / "classifier.onnx"),
                providers=["CPUExecutionProvider"],
            )
        else:
            raise ValueError(f"Unsupported shipped model: {self.shipped_model}")

    def predict(self, text: str) -> dict[str, Any]:
        """Predict one visitor message."""
        if self.shipped_model == "classical":
            probabilities = self.model.predict_proba([text])[0]
            class_order = self.model.classes_.tolist()
            scores = {
                label: float(probabilities[class_order.index(label)])
                if label in class_order
                else 0.0
                for label in self.labels
            }
        else:
            features = self.vectorizer.transform([text]).astype(np.float32).toarray()
            logits = self.onnx_session.run(None, {"features": features})[0]
            probabilities = _softmax(logits)[0]
            scores = {
                label: float(probabilities[idx])
                for idx, label in enumerate(self.labels)
            }

        label = max(scores, key=scores.get)
        confidence = scores[label]

        route_hint_by_label = {
            "spam": "drop",
            "question": "rag_search",
            "lead": "capture_lead",
            "escalate": "escalate",
        }

        route_hint = route_hint_by_label[label]
        if confidence < self.confidence_threshold:
            route_hint = "agent_handoff"

        return {
            "label": label,
            "confidence": confidence,
            "scores": scores,
            "model_version": self.model_version,
            "route_hint": route_hint,
        }
