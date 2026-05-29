"""FastAPI entry point — app factory, routers, lifespan."""

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.lifespan import lifespan

logger = structlog.get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(title="Concierge API", version="0.1.0", lifespan=lifespan)

    # lazy imports to avoid circular imports
    from app.api.auth import router as auth_router
    from app.api.chat import router as chat_router
    from app.api.content import router as content_router
    from app.api.escalations import router as escalations_router
    from app.api.leads import router as leads_router
    from app.api.tenants import router as tenants_router
    from app.api.widget import router as widget_router

    app.include_router(auth_router)
    app.include_router(tenants_router)
    app.include_router(content_router)
    app.include_router(chat_router)
    app.include_router(leads_router)
    app.include_router(escalations_router)
    app.include_router(widget_router)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> JSONResponse:
        return JSONResponse({"status": "ok"})

    return app


app = create_app()
