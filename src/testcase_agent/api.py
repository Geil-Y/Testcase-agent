from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .pipeline_console.router import console_html, router as console_router

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
    app.include_router(console_router, prefix=f"{settings.api_v1_prefix}/console")

    static_dir = Path(__file__).resolve().parents[2] / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/console", response_class=HTMLResponse)
    def serve_console():
        return HTMLResponse(console_html())

    return app


app = create_app()
