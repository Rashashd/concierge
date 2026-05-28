"""FastAPI entry point for the lean Concierge classifier model-server."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, status

from app.config import Settings, get_settings
from app.inference import IntentClassifier
from app.schemas import MetadataResponse, PredictRequest, PredictResponse

logger = structlog.get_logger(__name__)

ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "artifacts"


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_artifact_hashes(classifier: IntentClassifier) -> None:
    """Verify all artifact hashes pinned in classifier metadata."""
    expected_hashes: dict[str, str] = classifier.metadata.get("artifact_hashes", {})

    for filename, expected_hash in expected_hashes.items():
        path = ARTIFACT_DIR / filename
        if not path.exists():
            raise RuntimeError(f"Missing classifier artifact: {filename}")

        actual_hash = _sha256(path)
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"Artifact hash mismatch for {filename}: "
                f"expected={expected_hash} actual={actual_hash}"
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load the classifier once at startup."""
    settings = get_settings()
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(log_level))

    classifier = IntentClassifier()

    if settings.verify_artifact_hashes:
        _verify_artifact_hashes(classifier)

    app.state.classifier = classifier

    logger.info(
        "model_server.started",
        model_version=classifier.model_version,
        shipped_model=classifier.shipped_model,
    )

    yield

    logger.info("model_server.stopped")


app = FastAPI(
    title="Concierge Model Server",
    version="0.1.0",
    lifespan=lifespan,
)


async def require_service_token(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    """Require service-token authentication when configured."""
    expected = settings.model_server_service_token.get_secret_value()

    if not expected:
        return

    if authorization != f"Bearer {expected}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
        )


@app.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get(
    "/metadata",
    response_model=MetadataResponse,
    dependencies=[Depends(require_service_token)],
)
async def metadata() -> MetadataResponse:
    """Return classifier metadata."""
    classifier: IntentClassifier = app.state.classifier

    return MetadataResponse(
        model_version=classifier.model_version,
        shipped_model=classifier.shipped_model,
        confidence_threshold=classifier.confidence_threshold,
        labels=classifier.labels,
        serving_method=classifier.metadata.get("serving_method"),
    )


@app.post(
    "/predict",
    response_model=PredictResponse,
    dependencies=[Depends(require_service_token)],
)
async def predict(request: PredictRequest) -> PredictResponse:
    """Classify one visitor message."""
    classifier: IntentClassifier = app.state.classifier
    prediction: dict[str, Any] = classifier.predict(request.text)
    return PredictResponse.model_validate(prediction)
