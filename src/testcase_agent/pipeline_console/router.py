"""Pipeline Console API router — endpoints under /api/v1/console/..."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from ..config import get_settings

from .imports import (
    _unlink_temp,
    confirm_import,
    get_batch,
    get_latest_batch,
    list_batches_summary,
    preview_excel,
)
from .jobs import JobConflictError, get_job_runner
from .workbench import (
    load_clarification_review,
    save_and_advance_clarification,
    save_clarification_draft,
    start_run,
    validate_start_run,
)
from .runs import discover_runs, get_run

router = APIRouter()

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


# -- Non-API: Console UI shell ------------------------------------------------


def console_html() -> str:
    """Load the Console shell HTML template."""
    html_path = _TEMPLATE_DIR / "console.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<html><body><h1>Console not found</h1></body></html>"


# -- Import batch API --------------------------------------------------------


@router.get("/imports")
def list_imports():
    """List recent import batches (summaries only, no full requirements)."""
    return {"batches": list_batches_summary()}


@router.get("/imports/latest")
def latest_import():
    """Get the latest import batch with full requirements."""
    batch = get_latest_batch()
    if batch is None:
        return JSONResponse({"error": "No import batches found"}, status_code=404)
    return batch


@router.get("/imports/{batch_id}")
def get_import_batch(batch_id: str):
    """Get a specific import batch with full requirements."""
    batch = get_batch(batch_id)
    if batch is None:
        return JSONResponse({"error": f"Import batch '{batch_id}' not found"}, status_code=404)
    return batch


@router.post("/imports/preview")
async def import_preview(file: UploadFile):
    """Upload an Excel file and return sheet names + column headers for mapping."""
    suffix = Path(file.filename or "upload.xlsx").suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        shutil.copyfileobj(file.file, tmp)
        tmp.close()
        info = preview_excel(tmp.name)
        if info is None:
            _unlink_temp(tmp.name)
            return JSONResponse({"error": "Failed to read Excel file"}, status_code=400)
        return {
            "filename": file.filename,
            "sheets": info["sheets"],
            "columns": info["columns"],
            "tmp_path": tmp.name,
        }
    except Exception:
        _unlink_temp(tmp.name)
        return JSONResponse({"error": "Failed to read Excel file"}, status_code=500)


@router.post("/imports/confirm")
async def import_confirm(data: dict):
    """Confirm column mapping, parse requirements, persist as import batch."""
    tmp_path = data.get("tmp_path", "")
    sheet = data.get("sheet")
    mapping_data = data.get("mapping", {})
    filename = data.get("filename", "unknown.xlsx")

    if not tmp_path or not Path(tmp_path).exists():
        return JSONResponse({"error": "Uploaded file not found. Re-upload."}, status_code=400)

    try:
        batch = confirm_import(
            tmp_path=tmp_path,
            sheet=sheet,
            mapping_data=mapping_data,
            filename=filename,
        )
        return batch
    except Exception as e:
        _unlink_temp(tmp_path)
        return JSONResponse({"error": str(e)}, status_code=500)


# -- Mode labeling -----------------------------------------------------------


@router.get("/mode")
def console_mode():
    """Return the active LLM mode and visible label."""
    settings = get_settings()
    is_mock = settings.llm.provider == "mock"
    return {
        "provider": settings.llm.provider,
        "model": settings.llm.model_name,
        "mode": "mock" if is_mock else "real",
        "label": "MOCK MODE" if is_mock else f"Real — {settings.llm.provider} / {settings.llm.model_name}",
        "is_mock": is_mock,
    }


# -- Job runner --------------------------------------------------------------


@router.get("/jobs/current")
def get_current_job():
    """Get the current job status, or idle if none."""
    runner = get_job_runner()
    job = runner.get_job()
    if job is None:
        return {"status": "idle"}
    return {"status": "active", "job": job}


@router.get("/jobs/is-running")
def check_job_running():
    """Lightweight check: whether a job is running."""
    runner = get_job_runner()
    return {"running": runner.is_running()}


@router.post("/jobs/retry")
def retry_job():
    """Retry the last failed job."""
    runner = get_job_runner()
    try:
        job = runner.get_job()
        if job is None:
            return JSONResponse({"error": "No job to retry"}, status_code=400)
        # Re-run is handled by the caller providing the function
        return JSONResponse(
            {"error": "Retry requires a stage-specific endpoint (e.g. retry-clarification)"},
            status_code=400,
        )
    except JobConflictError as e:
        return JSONResponse({"error": str(e)}, status_code=409)


# -- Runs --------------------------------------------------------------------


@router.get("/runs")
def list_runs():
    """List all discovered runs."""
    return {"runs": discover_runs()}


@router.get("/runs/{run_dir_name}")
def get_run_info(run_dir_name: str):
    """Get run info with stage navigation and status."""
    info = get_run(run_dir_name)
    if info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)
    return info


@router.post("/runs/start")
def start_new_run(data: dict):
    """Start a new Active Run for a requirement (job-backed)."""
    runner = get_job_runner()
    requirement_key = data.get("requirement_key", "")
    batch_id = data.get("batch_id", "")

    if not requirement_key or not batch_id:
        return JSONResponse(
            {"error": "requirement_key and batch_id are required"},
            status_code=400,
        )

    # Check job locking first (before any expensive validation)
    if runner.is_running():
        return JSONResponse(
            {"error": "A job is already running. Wait for it to complete."},
            status_code=409,
        )

    # Pre-flight: validate batch and requirement exist
    try:
        validate_start_run(requirement_key, batch_id)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    try:
        job = runner.create_job(
            name=f"start-run-{requirement_key}",
        )

        def _run() -> dict:
            return start_run(requirement_key, batch_id)

        runner.start_job(job, _run)
        return {"status": "started", "job": job.to_dict()}

    except JobConflictError as e:
        return JSONResponse({"error": str(e)}, status_code=409)


# -- Clarification Review Workbench ------------------------------------------


@router.get("/runs/{run_dir_name}/clarification")
def get_clarification_review(run_dir_name: str):
    """Load the clarification review for editing in the workbench."""
    data = load_clarification_review(run_dir_name)
    if data is None:
        return JSONResponse(
            {"error": f"Clarification review not found for run '{run_dir_name}'"},
            status_code=404,
        )
    return data


@router.post("/runs/{run_dir_name}/clarification/draft")
def save_draft(run_dir_name: str, data: dict):
    """Save incomplete clarification review decisions without validation."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse(
            {"error": "A job is running. Editing is locked."},
            status_code=409,
        )

    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    decisions = data.get("decisions", [])
    try:
        result = save_clarification_draft(run_dir_name, decisions)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@router.post("/runs/{run_dir_name}/clarification/advance")
def advance_clarification(run_dir_name: str, data: dict):
    """Save, validate, and prepare case intent review (job-backed)."""
    runner = get_job_runner()

    if runner.is_running():
        return JSONResponse(
            {"error": "A job is already running. Wait for it to complete."},
            status_code=409,
        )

    decisions = data.get("decisions", [])

    # Pre-flight: check run exists
    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    try:
        job = runner.create_job(
            name=f"advance-clarification-{run_dir_name}",
            run_dir=run_dir_name,
        )

        def _run() -> dict:
            return save_and_advance_clarification(run_dir_name, decisions)

        runner.start_job(job, _run)
        return {"status": "started", "job": job.to_dict()}

    except JobConflictError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
