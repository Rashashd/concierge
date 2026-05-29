# ruff: noqa: E402
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.classifier_router import (
    ClassifierClient,
    ClassifierPrediction,
    resolve_chat_answer,
)

GOLDEN_PATH = Path(__file__).with_name("agent_golden.json")
AGENT_RESPONSE = "This is a test agent response."


class _FixedClassifier:
    def __init__(self, prediction: ClassifierPrediction) -> None:
        self._prediction = prediction

    async def predict(self, message: str) -> ClassifierPrediction:
        return self._prediction


class _RaisingClassifier:
    async def predict(self, message: str) -> ClassifierPrediction:
        raise RuntimeError("model-server timeout")


def _build_classifier(entry: dict[str, Any]) -> ClassifierClient | None:
    pred = entry["classifier_prediction"]

    if pred is None:
        return None

    if pred == "raise":
        return _RaisingClassifier()

    prediction = ClassifierPrediction.model_validate(pred)
    return _FixedClassifier(prediction)


class FakeMemory:
    def __init__(self) -> None:
        self.saved_turns: list[dict[str, str]] = []

    def save(self, user_message: str, assistant_message: str) -> None:
        self.saved_turns.append({"user": user_message, "assistant": assistant_message})


@dataclass
class ExampleResult:
    example_id: str
    passed: bool
    expected_action: str
    actual_action: str
    agent_called: bool
    agent_expected: bool
    memory_saved: bool
    phrase_checks: list[dict[str, Any]] = field(default_factory=list)
    detail: str = ""


async def _run_example(entry: dict[str, Any]) -> dict[str, Any]:
    example_id = entry["id"]
    message = entry["message"]
    expected_action = entry["expected_action"]
    expected_phrases: list[str] = entry["expected_answer_phrases"]
    should_call_agent: bool = entry["should_call_agent"]
    should_save_memory: bool = entry["should_save_memory"]

    classifier = _build_classifier(entry)
    memory = FakeMemory()

    agent_called = False

    async def run_agent() -> str:
        nonlocal agent_called
        agent_called = True
        return AGENT_RESPONSE

    answer, route = await resolve_chat_answer(
        classifier=classifier,
        message=message,
        run_agent=run_agent,
    )

    if should_save_memory:
        memory.save(message, answer)
    memory_saved = len(memory.saved_turns) > 0

    failures: list[str] = []

    if route.action != expected_action:
        failures.append(f"expected action '{expected_action}', got '{route.action}'")

    if agent_called != should_call_agent:
        failures.append(
            f"expected agent_called={should_call_agent}, got {agent_called}"
        )

    if should_save_memory and not memory_saved:
        failures.append("expected memory save but none occurred")
    if not should_save_memory and memory_saved:
        failures.append("expected no memory save but memory was written")

    phrase_checks: list[dict[str, Any]] = []
    for phrase in expected_phrases:
        found = phrase.lower() in answer.lower()
        phrase_checks.append({"phrase": phrase, "found": found})
        if not found:
            failures.append(f"answer missing expected phrase: '{phrase}'")

    return {
        "id": example_id,
        "passed": len(failures) == 0,
        "expected_action": expected_action,
        "actual_action": route.action,
        "agent_called": agent_called,
        "agent_expected": should_call_agent,
        "memory_saved": memory_saved,
        "answer_contains_phrases": phrase_checks,
        "detail": "; ".join(failures) if failures else "ok",
    }


async def run_eval(dataset_path: str | None = None) -> dict[str, Any]:
    path = Path(dataset_path) if dataset_path else GOLDEN_PATH
    dataset: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))

    for entry in dataset:
        if entry.get("tenant_id_source") != "verified_context":
            raise ValueError(
                f"Example '{entry['id']}' has tenant_id_source="
                f"'{entry.get('tenant_id_source')}', expected 'verified_context'"
            )

    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    for entry in dataset:
        result = await _run_example(entry)
        results.append(result)
        if result["passed"]:
            passed += 1
        else:
            failed += 1

    return {
        "example_count": len(dataset),
        "passed": passed,
        "failed": failed,
        "results": results,
        "failures": [r for r in results if not r["passed"]],
    }


if __name__ == "__main__":
    report = asyncio.run(run_eval())
    print(json.dumps(report, indent=2))
    if report["failed"] > 0:
        sys.exit(1)
