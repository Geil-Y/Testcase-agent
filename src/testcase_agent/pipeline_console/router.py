"""Pipeline Console API router — endpoints under /api/v1/console/..."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

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
    load_clarification_review,
    load_intent_review,
    save_and_advance_clarification,
    save_and_generate_cases,
    save_clarification_draft,
    save_intent_draft,
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
    """Retry the last failed job using its stored callable."""
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


# ── Issue #6: Review Workbench ergonomics ─────────────────────────────────


import json as _json


# -- Reason Codes ------------------------------------------------------------


@router.get("/reason-codes")
def get_reason_codes(review_type: str = "clarification"):
    """Return valid decisions, reason codes, and decision requirements for a review type."""
    from ..review_pipeline.reason_codes import (
        get_clarification_decisions,
        get_case_intent_decisions,
        get_reason_codes_for,
        get_decision_requirements,
    )

    if review_type == "clarification":
        decisions = get_clarification_decisions()
        item_type = "clarification_item"
    elif review_type == "case_intent":
        decisions = get_case_intent_decisions()
        item_type = "case_intent_item"
    else:
        return JSONResponse({"error": f"Unknown review_type: {review_type}"}, status_code=400)

    reason_codes = get_reason_codes_for(item_type)
    decision_reqs = {d: get_decision_requirements(d) for d in decisions}

    return {
        "review_type": review_type,
        "decisions": decisions,
        "reason_codes": reason_codes,
        "decision_requirements": decision_reqs,
    }


# -- Accept All Recommendations ----------------------------------------------


@router.post("/runs/{run_dir_name}/clarification/accept-recommendations")
def accept_all_recommendations(run_dir_name: str, data: dict):
    """Bulk-fill decisions with recommended values. Never saves or advances."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse(
            {"error": "A job is running. Editing is locked."},
            status_code=409,
        )

    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    run_path = Path(run_info["run_path"])
    review_path = run_path / "clarification_review.json"
    if not review_path.exists():
        return JSONResponse({"error": "Clarification review not found"}, status_code=404)

    review_data = _json.loads(review_path.read_text(encoding="utf-8"))
    force_confirm = data.get("confirm_high_risk", False)

    ambiguities = review_data.get("decomposition", {}).get("ambiguities", [])
    amb_by_id = {a.get("item_id"): a for a in ambiguities}

    proposed_decisions: list[dict[str, Any]] = []
    high_risk_items: list[str] = []

    for dec in review_data.get("decisions", []):
        if dec.get("decision", "").strip():
            continue

        amb = amb_by_id.get(dec.get("item_id"), {})
        recommended = amb.get("recommended_review_decision", "mark_needs_review")

        drivers = amb.get("confidence_drivers", {})
        vals = [v for v in drivers.values() if isinstance(v, (int, float))]
        confidence = (sum(vals) / len(vals)) if vals else 0.5
        is_high_risk = confidence < 0.65

        if not force_confirm and is_high_risk:
            high_risk_items.append(dec.get("item_id", "unknown"))
            continue
        if is_high_risk:
            high_risk_items.append(dec.get("item_id", "unknown"))

        proposed_decisions.append({
            "item_id": dec.get("item_id"),
            "decision": recommended,
        })

    if high_risk_items and not force_confirm:
        return {
            "proposed_decisions": proposed_decisions,
            "filled": len(proposed_decisions),
            "high_risk_skipped": len(high_risk_items),
            "high_risk_items": high_risk_items,
            "requires_confirmation": True,
            "saved": False,
            "message": (
                f"{len(high_risk_items)} orange/red items need confirmation. "
                "Submit with confirm_high_risk=true to accept all. "
                "Use Save Draft to persist."
            ),
        }

    # Return proposed decisions — never mutate the artifact directly.
    # The frontend applies these locally, then calls Save Draft to persist.
    return {
        "proposed_decisions": proposed_decisions,
        "filled": len(proposed_decisions),
        "high_risk_accepted": len(high_risk_items) if force_confirm else 0,
        "requires_confirmation": False,
        "saved": False,
        "message": "Proposed decisions returned. Use Save Draft (/clarification/draft) to persist.",
    }


# -- Filtered / sorted clarification review ----------------------------------


def _routing_for_confidence(score: float) -> str:
    if score >= 0.85:
        return "green"
    elif score >= 0.65:
        return "blue"
    elif score >= 0.40:
        return "orange"
    return "red"


def _guess_confidence(amb: dict) -> float:
    drivers = amb.get("confidence_drivers", {})
    if not drivers:
        return 0.5
    vals = [v for v in drivers.values() if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else 0.5


@router.get("/runs/{run_dir_name}/clarification/filtered")
def get_filtered_clarification(
    run_dir_name: str,
    decision_filter: str = "",
    routing_filter: str = "",
    search: str = "",
    sort: str = "priority",
):
    """Load clarification review with filtering, sorting, and search."""
    data = load_clarification_review(run_dir_name)
    if data is None:
        return JSONResponse(
            {"error": f"Clarification review not found for run '{run_dir_name}'"},
            status_code=404,
        )

    decisions = data.get("review", {}).get("decisions", [])
    ambiguities = data.get("review", {}).get("decomposition", {}).get("ambiguities", [])

    amb_by_id = {a.get("item_id"): a for a in ambiguities}

    enriched = []
    for d in decisions:
        item_id = d.get("item_id", "")
        amb = amb_by_id.get(item_id, {})
        enriched.append({
            **d,
            "ambiguity_type": amb.get("ambiguity_type", ""),
            "recommended_decision": amb.get("recommended_review_decision", ""),
            "routing_color": _routing_for_confidence(
                d.get("confidence_before_review") or _guess_confidence(amb)
            ),
            "affected_text": amb.get("affected_text", ""),
            "impact": amb.get("impact", ""),
            "severity": amb.get("severity", ""),
            "clarification_question": amb.get("clarification_question", ""),
        })

    if decision_filter:
        enriched = [
            e for e in enriched
            if e.get("decision") == decision_filter or (not e.get("decision") and decision_filter == "pending")
        ]

    if routing_filter:
        enriched = [e for e in enriched if e.get("routing_color") == routing_filter]

    if search:
        q = search.lower()
        enriched = [
            e for e in enriched
            if q in _json.dumps(e).lower()
        ]

    if sort == "priority":
        def _sort_key(e):
            is_pending = 0 if not e.get("decision") else 1
            routing_order = {"red": 0, "orange": 1, "blue": 2, "green": 3}
            routing_rank = routing_order.get(e.get("routing_color", "blue"), 2)
            return (is_pending, routing_rank, e.get("item_id", ""))
        enriched.sort(key=_sort_key)

    enriched_review = {**data.get("review", {}), "decisions": enriched}

    return {
        "run": data.get("run"),
        "review": enriched_review,
        "filters": {
            "decision_filter": decision_filter,
            "routing_filter": routing_filter,
            "search": search,
            "sort": sort,
        },
        "total": len(enriched),
    }


# -- Review Memory hints -----------------------------------------------------


@router.get("/runs/{run_dir_name}/memory-hints")
def get_memory_hints(run_dir_name: str):
    """Return advisory Review Memory hints. Never auto-selects decisions."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    run_path = Path(run_info["run_path"])
    hints: list[str] = []
    adjustment = 0.0

    # Try to load requirement hash and tags from run artifacts
    try:
        from ..review_pipeline.storage.store import compute_historical_support
        from ..review_pipeline.tag_rules.pattern_tag_rules import derive_all_tags

        review_file = run_path / "clarification_review.json"
        if review_file.exists():
            data = _json.loads(review_file.read_text(encoding="utf-8"))
            source_hash = data.get("source_requirement_hash", "")

            # Derive tags from existing data
            tags = derive_all_tags(data)
            tag_names = [t.get("tag", "") for t in tags if isinstance(t, dict)]

            if source_hash or tag_names:
                support = compute_historical_support(source_hash, tag_names)
                hints = support.get("hints", [])
                adjustment = support.get("adjustment", 0.0)
    except Exception:
        pass  # Memory DB may not exist; hints remain empty

    return {
        "run": run_dir_name,
        "hints": hints,
        "adjustment": adjustment,
        "advisory_note": (
            "Review Memory hints are advisory only. "
            "They never auto-select decisions, generate reason text, or mutate review artifacts."
        ),
    }


# ── Issue #9: Read-only Results, export, and Review Memory import ──────────


@router.get("/runs/{run_dir_name}/results")
def get_results(run_dir_name: str):
    """Return read-only generated cases and evaluation results."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    run_path = Path(run_info["run_path"])
    cases_path = run_path / "generated_cases.json"
    eval_path = run_path / "evaluation_summary.json"
    eval_detail_path = run_path / "evaluation_results.json"

    cases = None
    if cases_path.exists():
        cases = _json.loads(cases_path.read_text(encoding="utf-8"))

    evaluation = None
    if eval_path.exists():
        evaluation = _json.loads(eval_path.read_text(encoding="utf-8"))

    eval_detail = None
    if eval_detail_path.exists():
        eval_detail = _json.loads(eval_detail_path.read_text(encoding="utf-8"))

    return {
        "run": run_info,
        "cases": cases,
        "evaluation": evaluation,
        "evaluation_detail": eval_detail,
        "read_only": True,
        "note": "Results are read-only. To change cases, revise upstream review decisions and regenerate.",
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
        return JSONResponse(
            {"error": f"Artifact '{artifact_name}' not found"},
            status_code=404,
        )

    allowed = {
        "00_requirements.json", "clarification_review.json",
        "clarified_test_basis.json", "case_intent_review.json",
        "approved_case_plan.json", "generated_cases.json",
        "evaluation_summary.json", "evaluation_results.json",
    }
    if artifact_name not in allowed:
        return JSONResponse(
            {"error": f"Artifact '{artifact_name}' not available for download"},
            status_code=400,
        )

    content = _json.loads(artifact_path.read_text(encoding="utf-8"))
    return {"artifact": artifact_name, "content": content}


@router.get("/runs/{run_dir_name}/export")
def export_run(run_dir_name: str, include_archived: bool = False):
    """Export the active run as a bundle. Archived artifacts excluded by default."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    run_path = Path(run_info["run_path"])
    bundle: dict[str, Any] = {
        "run": run_info,
        "active_artifacts": {},
        "archived_artifacts": [],
    }

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


@router.post("/runs/{run_dir_name}/import-memory")
def import_review_memory(run_dir_name: str):
    """Explicitly import Review Memory from a completed run. Never automatic."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    run_path = Path(run_info["run_path"])

    try:
        from ..review_pipeline.storage import store
        store.import_memory(str(run_path))
        return {
            "imported": True,
            "run": run_dir_name,
            "message": "Review Memory imported successfully.",
        }
    except Exception as e:
        return JSONResponse(
            {"error": f"Review Memory import failed: {e}"},
            status_code=500,
        )


# ── Issue #8: Regeneration and downstream artifact reuse ───────────────────


@router.post("/runs/{run_dir_name}/regenerate")
def regenerate_route(run_dir_name: str, data: dict):
    """Archive downstream artifacts and regenerate after upstream changes."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse({"error": "A job is already running."}, status_code=409)

    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    run_path = Path(run_info["run_path"])
    stage = data.get("stage", "")
    confirmed = data.get("confirm", False)

    if stage not in ("clarification", "intents", "cases"):
        return JSONResponse(
            {"error": f"Unknown stage: {stage}. Use clarification, intents, or cases."},
            status_code=400,
        )

    upstream_map = {
        "clarification": "clarification_review.json",
        "intents": "clarified_test_basis.json",
        "cases": "approved_case_plan.json",
    }
    upstream_artifact = upstream_map[stage]

    if not (run_path / upstream_artifact).exists():
        return JSONResponse(
            {"error": f"Upstream artifact '{upstream_artifact}' not found"},
            status_code=404,
        )

    affected = artifacts_to_archive(upstream_artifact, run_path)

    if not confirmed:
        return {
            "confirmation_required": True,
            "stage": stage,
            "upstream_artifact": upstream_artifact,
            "affected_artifacts": affected,
            "message": f"This will archive {len(affected)} downstream artifacts. Submit with confirm=true.",
        }

    archive_artifacts(run_path, affected)

    try:
        job = runner.create_job(
            name=f"regenerate-{stage}-{run_dir_name}",
            run_dir=run_dir_name,
        )

        def _run() -> dict:
            if stage == "clarification":
                return _regenerate_clarification(run_path)
            elif stage == "intents":
                return _regenerate_intents(run_path)
            elif stage == "cases":
                return _regenerate_cases(run_path)
            return {"error": f"Unknown stage: {stage}"}

        runner.start_job(job, _run)
        return {"status": "started", "job": job.to_dict(), "archived": affected}

    except JobConflictError as e:
        return JSONResponse({"error": str(e)}, status_code=409)


def _regenerate_clarification(run_path: Path) -> dict:
    """Re-validate clarification_review.json, produce clarified_test_basis,
    then prepare intent review. Handles validation failure and blocked state."""
    from ..review_pipeline.stages.validate_clarification import validate_clarification_review
    from ..review_pipeline.stages.plan_case_intents import prepare_intent_review

    review_path = str(run_path / "clarification_review.json")
    validation, basis = validate_clarification_review(review_path)

    if not validation.is_valid:
        return {
            "regenerated": "clarification",
            "status": "validation_failed",
            "errors": [
                {"artifact_path": e.artifact_path, "field_path": e.field_path, "message": e.message}
                for e in validation.errors
            ],
        }

    if basis is None:
        return {"regenerated": "clarification", "status": "failed", "error": "No clarified test basis produced"}

    if basis.blocked:
        return {
            "regenerated": "clarification",
            "status": "blocked",
            "block_reasons": basis.block_reasons,
        }

    # clarified_test_basis.json was written by validate_clarification_review
    settings = get_settings()
    provider = create_provider(settings)
    prepare_intent_review(str(run_path), provider=provider, memory_hints=None)

    return {
        "regenerated": "clarification",
        "status": "succeeded",
        "artifacts": _list_active(run_path),
        "run_dir": run_path.name,
    }


def _regenerate_intents(run_path: Path) -> dict:
    """Re-validate case_intent_review.json, produce approved_case_plan,
    then generate cases."""
    from ..review_pipeline.stages.validate_case_intent import validate_case_intent_review
    from ..review_pipeline.stages.write_cases import generate_cases

    review_path = str(run_path / "case_intent_review.json")
    validation, plan = validate_case_intent_review(review_path)

    if not validation.is_valid:
        return {
            "regenerated": "intents",
            "status": "validation_failed",
            "errors": [
                {"artifact_path": e.artifact_path, "field_path": e.field_path, "message": e.message}
                for e in validation.errors
            ],
        }

    if plan is None:
        return {"regenerated": "intents", "status": "failed", "error": "No approved plan produced"}

    settings = get_settings()
    provider = create_provider(settings)
    case_set = generate_cases(str(run_path), provider=provider)

    return {
        "regenerated": "intents",
        "status": "succeeded",
        "case_count": len(case_set.cases),
        "artifacts": _list_active(run_path),
        "run_dir": run_path.name,
    }


def _regenerate_cases(run_path: Path) -> dict:
    """Re-generate cases and evaluate."""
    from ..review_pipeline.stages.write_cases import generate_cases
    from ..review_pipeline.stages.evaluate import evaluate_run

    settings = get_settings()
    provider = create_provider(settings)
    case_set = generate_cases(str(run_path), provider=provider)
    evaluate_run(str(run_path))

    return {
        "regenerated": "cases",
        "status": "succeeded",
        "case_count": len(case_set.cases),
        "artifacts": _list_active(run_path),
        "run_dir": run_path.name,
    }


def _list_active(run_path: Path) -> list[str]:
    return sorted(
        f.name for f in run_path.iterdir()
        if f.is_file() and f.suffix == ".json" and "archived" not in str(f)
    )


# ── Issue #7: Case Intent Review and case generation ──────────────────────


@router.get("/runs/{run_dir_name}/intents")
def get_intent_review(run_dir_name: str):
    """Load the case intent review for editing."""
    data = load_intent_review(run_dir_name)
    if data is None:
        return JSONResponse(
            {"error": f"Case intent review not found for run '{run_dir_name}'"},
            status_code=404,
        )
    return data


@router.post("/runs/{run_dir_name}/intents/draft")
def save_intent_draft_route(run_dir_name: str, data: dict):
    """Save incomplete case intent review decisions without validation."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse({"error": "A job is running. Editing is locked."}, status_code=409)

    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    decisions = data.get("decisions", [])
    try:
        result = save_intent_draft(run_dir_name, decisions)
        return result
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)


@router.post("/runs/{run_dir_name}/intents/generate")
def generate_cases_route(run_dir_name: str, data: dict):
    """Save, validate, generate cases, evaluate (job-backed)."""
    runner = get_job_runner()
    if runner.is_running():
        return JSONResponse({"error": "A job is already running."}, status_code=409)

    run_info = get_run(run_dir_name)
    if run_info is None:
        return JSONResponse({"error": f"Run '{run_dir_name}' not found"}, status_code=404)

    decisions = data.get("decisions", [])

    try:
        job = runner.create_job(
            name=f"generate-cases-{run_dir_name}",
            run_dir=run_dir_name,
        )

        def _run() -> dict:
            return save_and_generate_cases(run_dir_name, decisions)

        runner.start_job(job, _run)
        return {"status": "started", "job": job.to_dict()}

    except JobConflictError as e:
        return JSONResponse({"error": str(e)}, status_code=409)
