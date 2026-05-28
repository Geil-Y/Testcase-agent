"""Pipeline Console API router — simplified A/B/C reviewed pipeline endpoints."""

from __future__ import annotations

import json as _json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from ..config import get_settings
from ..provider.factory import create_provider

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
    load_extraction,
    load_intents,
    load_cases,
    save_extraction_review,
    save_intent_review,
    save_case_edit,
    accept_extraction_all,
    accept_intents_all,
    accept_cases_all,
    plan_and_load_intents,
    generate_and_load_cases,
    regenerate_cases,
    start_run,
    validate_start_run,
)
from .runs import (
    archive_artifacts,
    artifact_hash,
    artifacts_to_archive,
    content_hash,
    discover_runs,
    get_run,
    has_changed,
)
from .trace import read_trace_events

router = APIRouter()

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


# -- Non-API: Console UI shell ------------------------------------------------

def console_html() -> str:
    html_path = _TEMPLATE_DIR / "console.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<html><body><h1>Console not found</h1></body></html>"


# -- Import batch API --------------------------------------------------------

@router.get("/imports")
def list_imports():
    return {"batches": list_batches_summary()}


@router.get("/imports/latest")
def latest_import():
    batch = get_latest_batch()
    if batch is None:
        return JSONResponse({"error": "No import batches found"}, status_code=404)
    return batch


@router.get("/imports/{batch_id}")
def get_import_batch(batch_id: str):
    batch = get_batch(batch_id)
    if batch is None:
        return JSONResponse({"error": f"Import batch '{batch_id}' not found"}, status_code=404)
    return batch


@router.post("/imports/preview")
async def import_preview(file: UploadFile):
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
    tmp_path = data.get("tmp_path", "")
    sheet = data.get("sheet")
    mapping_data = data.get("mapping", {})
    filename = data.get("filename", "unknown.xlsx")

    if not tmp_path or not Path(tmp_path).exists():
        return JSONResponse({"error": "Uploaded file not found. Re-upload."}, status_code=400)

    try:
        batch = confirm_import(
            tmp_path=tmp_path, sheet=sheet, mapping_data=mapping_data, filename=filename)
        return batch
    except Exception as e:
        _unlink_temp(tmp_path)
        return JSONResponse({"error": str(e)}, status_code=500)


# -- Mode labeling -----------------------------------------------------------

@router.get("/mode")
def console_mode():
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
    runner = get_job_runner()
    job = runner.get_job()
    if job is None:
        return {"status": "idle"}
    if job.get("status") in ("succeeded", "failed"):
        return {"status": "idle", "last_job": job}
    return {"status": "active", "job": job}


@router.get("/jobs/is-running")
def check_job_running():
    runner = get_job_runner()
    return {"running": runner.is_running()}


@router.post("/jobs/retry")
def retry_job():
    runner = get_job_runner()
    try:
        retried = runner.retry_job()
        return {"status": "retried", "job": retried.to_dict()}
    except JobConflictError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# -- Runs --------------------------------------------------------------------

@router.get("/runs")
def list_runs():
    return {"runs": discover_runs()}


@router.get("/runs/{run_dir_name}")
def get_run_info(run_dir_name: str):
    info = get_run(run_dir_name)
    if info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)
    return info


@router.get("/runs/{run_dir_name}/trace")
def get_trace_events(run_dir_name: str):
    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)
    events = read_trace_events(str(run_info["run_path"]))
    return {"run_dir": run_dir_name, "events": events}


@router.post("/runs/start")
def start_new_run(data: dict):
    """Start a new Active Run — runs LLM-A extraction."""
    runner = get_job_runner()
    requirement_key = data.get("requirement_key", "")
    batch_id = data.get("batch_id", "")

    if not requirement_key or not batch_id:
        return JSONResponse({"error": "requirement_key and batch_id are required"}, status_code=400)

    if runner.is_running():
        return JSONResponse({"error": "A job is already running."}, status_code=409)

    try:
        validate_start_run(requirement_key, batch_id)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

    try:
        job = runner.create_job(name=f"start-run-{requirement_key}")
        def _run() -> dict:
            return start_run(requirement_key, batch_id)
        runner.start_job(job, _run)
        return {"status": "started", "job": job.to_dict()}
    except JobConflictError as e:
        return JSONResponse({"error": str(e)}, status_code=409)


# -- Extraction (LLM-A) review -----------------------------------------------

@router.get("/runs/{run_dir_name}/extraction")
def get_extraction(run_dir_name: str):
    """Load the extracted test basis for review."""
    data = load_extraction(run_dir_name)
    if data is None:
        return JSONResponse(
            {"error": f"Extraction not found for run '{run_dir_name}'"}, status_code=404)
    return data


@router.post("/runs/{run_dir_name}/extraction/review")
def save_extraction(run_dir_name: str, data: dict):
    """Save extraction review actions and write reviewed_extracted_test_basis.json."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse({"error": "A job is running. Editing is locked."}, status_code=409)

    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    actions = data.get("actions", [])
    try:
        result = save_extraction_review(run_dir_name, actions)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@router.post("/runs/{run_dir_name}/extraction/accept-all")
def accept_extraction(run_dir_name: str):
    """Accept All: write reviewed_extracted_test_basis.json."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse({"error": "A job is running."}, status_code=409)

    try:
        result = accept_extraction_all(run_dir_name)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# -- Case intents (LLM-B) ----------------------------------------------------

@router.post("/runs/{run_dir_name}/intents/plan")
def plan_intents_route(run_dir_name: str):
    """Run LLM-B to plan case intents from reviewed extraction."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse({"error": "A job is already running."}, status_code=409)

    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    try:
        job = runner.create_job(name=f"plan-intents-{run_dir_name}", run_dir=run_dir_name)
        def _run() -> dict:
            return plan_and_load_intents(run_dir_name)
        runner.start_job(job, _run)
        return {"status": "started", "job": job.to_dict()}
    except JobConflictError as e:
        return JSONResponse({"error": str(e)}, status_code=409)


@router.get("/runs/{run_dir_name}/intents")
def get_intents(run_dir_name: str):
    """Load the case intents for review."""
    data = load_intents(run_dir_name)
    if data is None:
        return JSONResponse(
            {"error": f"Case intents not found for run '{run_dir_name}'"}, status_code=404)
    return data


@router.post("/runs/{run_dir_name}/intents/review")
def save_intents(run_dir_name: str, data: dict):
    """Save intent review actions and write reviewed_case_intents.json."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse({"error": "A job is running. Editing is locked."}, status_code=409)

    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    actions = data.get("actions", [])
    try:
        result = save_intent_review(run_dir_name, actions)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@router.post("/runs/{run_dir_name}/intents/accept-all")
def accept_intents(run_dir_name: str):
    """Accept All: write reviewed_case_intents.json."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse({"error": "A job is running."}, status_code=409)

    try:
        result = accept_intents_all(run_dir_name)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# -- Case generation (LLM-C) -------------------------------------------------

@router.post("/runs/{run_dir_name}/cases/generate")
def generate_cases_route(run_dir_name: str):
    """Run LLM-C to generate test cases from reviewed artifacts."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse({"error": "A job is already running."}, status_code=409)

    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    try:
        job = runner.create_job(name=f"generate-cases-{run_dir_name}", run_dir=run_dir_name)
        def _run() -> dict:
            return generate_and_load_cases(run_dir_name)
        runner.start_job(job, _run)
        return {"status": "started", "job": job.to_dict()}
    except JobConflictError as e:
        return JSONResponse({"error": str(e)}, status_code=409)


@router.get("/runs/{run_dir_name}/cases")
def get_cases(run_dir_name: str):
    """Load generated or reviewed cases."""
    data = load_cases(run_dir_name)
    if data is None:
        return JSONResponse(
            {"error": f"Cases not found for run '{run_dir_name}'"}, status_code=404)
    return data


@router.post("/runs/{run_dir_name}/cases/accept-all")
def accept_cases(run_dir_name: str):
    """Accept All: write reviewed_cases.json."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse({"error": "A job is running."}, status_code=409)

    try:
        result = accept_cases_all(run_dir_name)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.post("/runs/{run_dir_name}/cases/edit")
def edit_cases_route(run_dir_name: str, data: dict):
    """Save manually edited cases as reviewed_cases.json."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse({"error": "A job is running. Editing is locked."}, status_code=409)

    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    cases = data.get("cases", [])
    try:
        result = save_case_edit(run_dir_name, cases)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@router.post("/runs/{run_dir_name}/cases/regenerate")
def regenerate_cases_route(run_dir_name: str, data: dict):
    """Regenerate case(s) with review comment(s)."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse({"error": "A job is already running."}, status_code=409)

    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    requests = data.get("requests", [])
    try:
        result = regenerate_cases(run_dir_name, requests)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


# -- Results / Export --------------------------------------------------------

@router.get("/runs/{run_dir_name}/results")
def get_results(run_dir_name: str):
    """Return read-only cases (preferring reviewed_cases.json when available)."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    run_path = Path(run_info["run_path"])

    # Prefer reviewed cases, fall back to generated
    reviewed_path = run_path / "reviewed_cases.json"
    generated_path = run_path / "generated_cases.json"

    cases = None
    reviewed = False
    if reviewed_path.exists():
        cases = _json.loads(reviewed_path.read_text(encoding="utf-8"))
        reviewed = True
    elif generated_path.exists():
        cases = _json.loads(generated_path.read_text(encoding="utf-8"))
        reviewed = False

    return {
        "run": run_info,
        "cases": cases,
        "reviewed": reviewed,
        "read_only": True,
        "note": "Results are read-only. Use review endpoints to accept or edit cases.",
    }


@router.get("/runs/{run_dir_name}/artifacts/{artifact_name}")
def download_artifact(run_dir_name: str, artifact_name: str):
    """Download a single active artifact from a run."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    run_path = Path(run_info["run_path"])
    artifact_path = run_path / artifact_name

    if not artifact_path.exists():
        return JSONResponse({"error": f"Artifact '{artifact_name}' not found"}, status_code=404)

    # Allow new artifact names + legacy names for download-only
    allowed = {
        "00_requirements.json",
        "extracted_test_basis.json", "reviewed_extracted_test_basis.json",
        "case_intents.json", "reviewed_case_intents.json",
        "generated_cases.json", "reviewed_cases.json",
        "evaluation_summary.json", "evaluation_results.json",
    }
    if artifact_name not in allowed:
        return JSONResponse({"error": f"Artifact '{artifact_name}' not available"}, status_code=400)

    content = _json.loads(artifact_path.read_text(encoding="utf-8"))
    return {"artifact": artifact_name, "content": content}


@router.get("/runs/{run_dir_name}/export")
def export_run(run_dir_name: str, include_archived: bool = False):
    """Export the active run as a bundle."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    run_path = Path(run_info["run_path"])
    bundle: dict[str, Any] = {"run": run_info, "active_artifacts": {}, "archived_artifacts": []}

    for f in sorted(run_path.iterdir()):
        if not f.is_file() or not f.suffix == ".json":
            continue
        if f.parent.name == "archived" or "archived" in str(f):
            continue
        try:
            bundle["active_artifacts"][f.name] = _json.loads(f.read_text(encoding="utf-8"))
        except (_json.JSONDecodeError, OSError):
            pass

    if include_archived:
        archive_root = run_path / "archived"
        if archive_root.exists():
            for ts_dir in sorted(archive_root.iterdir()):
                if not ts_dir.is_dir():
                    continue
                entry: dict[str, Any] = {"timestamp": ts_dir.name, "artifacts": {}}
                for f in sorted(ts_dir.iterdir()):
                    if f.suffix == ".json":
                        try:
                            entry["artifacts"][f.name] = _json.loads(f.read_text(encoding="utf-8"))
                        except (_json.JSONDecodeError, OSError):
                            pass
                bundle["archived_artifacts"].append(entry)

    return bundle


# -- Legacy endpoints (kept for backward compat, redirect to extraction) -----

@router.get("/runs/{run_dir_name}/clarification")
def get_clarification_redirect(run_dir_name: str):
    """[DEPRECATED] Redirect to extraction endpoint."""
    return get_extraction(run_dir_name)


def _list_active(run_path: Path) -> list[str]:
    return sorted(
        f.name for f in run_path.iterdir()
        if f.is_file() and f.suffix == ".json" and "archived" not in str(f)
    )
