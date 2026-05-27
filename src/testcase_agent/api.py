from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .pipeline_console.router import console_html, router as console_router

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
            # /assets covers ./assets/ when page URL is /console (no trailing slash)
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="console_assets")

        @app.get("/console/assets/{file_path:path}")
        def serve_console_asset(file_path: str):
            """Serve Vite-built assets referenced by the React shell."""
            asset = _CONSOLE_UI_DIST / "assets" / file_path
            if asset.exists() and asset.is_file():
                return FileResponse(str(asset))
            return HTMLResponse("Not found", status_code=404)

        @app.get("/console", response_class=HTMLResponse)
        @app.get("/console/{rest_path:path}", response_class=HTMLResponse)
        def serve_console(rest_path: str = ""):
            """Serve the React Console shell.

            If the Vite build exists at console-ui/dist/index.html, serve it.
            Otherwise fall back to the legacy single-file console.html template.
            """
            index_path = _CONSOLE_UI_DIST / "index.html"
            if index_path.exists():
                html = index_path.read_text(encoding="utf-8")
                return HTMLResponse(html)
            return HTMLResponse(console_html())

    else:
        @app.get("/console", response_class=HTMLResponse)
        def serve_console_legacy():
            return HTMLResponse(console_html())

    return app


app = create_app()
