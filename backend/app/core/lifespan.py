from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.core.config import get_settings
from app.infra.llm import get_llm

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.llm = get_llm(settings)
    logger.info("backend.started")
    try:
        yield
    finally:
        logger.info("backend.stopped")
