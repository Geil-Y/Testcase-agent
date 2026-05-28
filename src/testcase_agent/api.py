from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .pipeline_console.router import router as console_router

root_router = APIRouter()

# Path to the React/Vite build output
_CONSOLE_UI_DIST = Path(__file__).resolve().parents[2] / "console-ui" / "dist"


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

    # Legacy static dir (images etc.)
    static_dir = Path(__file__).resolve().parents[2] / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    if _CONSOLE_UI_DIST.exists():
        assets_dir = _CONSOLE_UI_DIST / "assets"
        if assets_dir.exists():
            app.mount("/console/assets", StaticFiles(directory=str(assets_dir)), name="console_assets")

        @app.get("/console", response_class=HTMLResponse)
        @app.get("/console/{rest_path:path}", response_class=HTMLResponse)
        def serve_console(rest_path: str = ""):
            """Serve the React Console shell from the Vite build output."""
            index_path = _CONSOLE_UI_DIST / "index.html"
            if index_path.exists():
                html = index_path.read_text(encoding="utf-8")
                return HTMLResponse(html)
            return HTMLResponse(
                "<html><body><h1>Console not found</h1>"
                "<p>Run <code>npm run build</code> in <code>console-ui/</code> to build the React Console.</p>"
                "</body></html>"
            )

    else:
        @app.get("/console", response_class=HTMLResponse)
        @app.get("/console/{rest_path:path}", response_class=HTMLResponse)
        def serve_console_legacy(rest_path: str = ""):
            return HTMLResponse(
                "<html><body><h1>Console not found</h1>"
                "<p>Run <code>npm run build</code> in <code>console-ui/</code> to build the React Console.</p>"
                "</body></html>"
            )

    return app


app = create_app()
