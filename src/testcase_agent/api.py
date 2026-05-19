from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, FastAPI, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .pipeline.generate import RequirementInput, run_pipeline
from .pipeline.import_requirements import ColumnMapping, list_columns, list_sheets, parse_requirements
from .provider.factory import create_provider
from .quality.gate import evaluate_cases

router = APIRouter()

# In-memory state for the sandbox session
_state: dict = {
    "requirements": [],
    "results": {},
}


@router.get("/health")
def health():
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "llm_provider": settings.llm.provider,
        "llm_model": settings.llm.model_name,
    }


@router.post("/import/preview")
async def import_preview(file: UploadFile):
    """Upload an Excel file and return sheet names + column headers for mapping."""
    suffix = Path(file.filename or "upload.xlsx").suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()
        sheets = list_sheets(tmp.name)
        columns = list_columns(tmp.name, sheets[0] if sheets else None)
        Path(tmp.name).unlink()
        return {
            "filename": file.filename,
            "sheets": sheets,
            "columns": columns,
            "tmp_path": tmp.name,
        }
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        return {"error": "Failed to read Excel file"}


@router.post("/import/confirm")
async def import_confirm(data: dict):
    """Confirm column mapping and parse requirements from the uploaded Excel."""
    tmp_path = data.get("tmp_path", "")
    sheet = data.get("sheet")
    mapping_data = data.get("mapping", {})

    if not tmp_path or not Path(tmp_path).exists():
        return {"error": "Uploaded file not found. Re-upload."}

    mapping = ColumnMapping(
        requirement_key_col=mapping_data.get("requirement_key_col", ""),
        description_col=mapping_data.get("description_col", ""),
        function_name_col=mapping_data.get("function_name_col", ""),
        requirement_type_col=mapping_data.get("requirement_type_col", ""),
        supplementary_info_cols=mapping_data.get("supplementary_info_cols", []),
    )

    try:
        reqs = parse_requirements(tmp_path, mapping, sheet or None)
        Path(tmp_path).unlink(missing_ok=True)
        _state["requirements"] = reqs
        req_list = [
            {
                "id": i,
                "requirement_key": r.requirement_key,
                "description": r.description[:120],
                "function_name": r.function_name,
                "requirement_type": r.requirement_type,
                "is_heading": r.is_heading,
                "is_info": r.is_info,
            }
            for i, r in enumerate(reqs)
        ]
        return {"requirements": req_list, "count": len(req_list)}
    except Exception as e:
        Path(tmp_path).unlink(missing_ok=True)
        return {"error": str(e)}


@router.post("/generate/{req_id}")
def generate(req_id: int):
    """Generate test cases for a requirement by its index."""
    reqs = _state.get("requirements", [])
    if req_id < 0 or req_id >= len(reqs):
        return {"error": "Requirement not found"}

    req = reqs[req_id]
    if req.is_heading or req.is_info:
        return {"error": f"Cannot generate cases for type '{req.requirement_type}'"}

    settings = get_settings()
    provider = create_provider(settings)

    req_input = RequirementInput(
        requirement_key=req.requirement_key,
        description=req.description,
        function_name=req.function_name,
        supplementary_info=req.supplementary_info,
    )

    result = run_pipeline(req_input, provider)
    if result.error:
        return {"error": result.error}

    quality_reports = evaluate_cases(result.cases)

    cases_data = []
    for case, report in zip(result.cases, quality_reports):
        cases_data.append({
            "title": case.title,
            "objective": case.objective,
            "precondition": case.precondition,
            "postcondition": case.postcondition,
            "steps": [{"order": s.order, "action": s.action, "expected": s.expected} for s in case.steps],
            "raw_html": case.raw_html,
            "quality": {
                "passed": report.passed,
                "failures": report.failures,
                "warnings": report.warnings,
            },
        })

    _state["results"][req_id] = {
        "analysis": {
            "signals": result.analysis.signals if result.analysis else [],
            "thresholds": result.analysis.thresholds if result.analysis else [],
            "timing": result.analysis.timing if result.analysis else [],
            "direction": result.analysis.direction if result.analysis else "",
            "case_intents": [
                {"coverage": i.coverage, "description": i.description}
                for i in (result.analysis.case_intents if result.analysis else [])
            ],
            "raw_html": result.analysis.raw_html if result.analysis else "",
        },
        "cases": cases_data,
    }

    return _state["results"][req_id]


@router.get("/results/{req_id}")
def get_results(req_id: int):
    """Get previously generated results for a requirement."""
    if req_id not in _state.get("results", {}):
        return {"error": "No results for this requirement"}
    return _state["results"][req_id]


@router.get("/sandbox")
def sandbox():
    """Serve the sandbox UI."""
    static_dir = Path(__file__).resolve().parents[2] / "static"
    html_path = static_dir / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.include_router(router, prefix=settings.api_v1_prefix)
    static_dir = Path(__file__).resolve().parents[2] / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app


app = create_app()
