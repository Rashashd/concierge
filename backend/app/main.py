from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.api.widget import router as widget_router
from app.core.lifespan import lifespan


def create_app() -> FastAPI:
    app = FastAPI(title="Concierge API", lifespan=lifespan)
    app.include_router(chat_router)
    app.include_router(widget_router)
    return app


app = create_app()
