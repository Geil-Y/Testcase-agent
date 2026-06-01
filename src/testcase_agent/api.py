from __future__ import annotations

from fastapi import APIRouter, FastAPI

from .config import get_settings

root_router = APIRouter()


@root_router.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm_provider": settings.llm.provider,
        "llm_model": settings.llm.model_name,
    }


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.include_router(root_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
