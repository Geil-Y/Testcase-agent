"""Review Workbench — Console bridge to review pipeline stage functions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..provider.factory import create_provider
from ..review_pipeline.artifacts.io import read_json, write_json
from ..review_pipeline.artifacts.models import (
    ClarificationReview,
    ClarifiedTestBasis,
)
from ..review_pipeline.artifacts.validation import ValidationError, ValidationResult
from ..review_pipeline.stages.decompose_requirement import prepare_clarification_review
from ..review_pipeline.stages.validate_clarification import validate_clarification_review
from .imports import get_batch
from .runs import (
    make_run_dir,
    write_run_input,
    get_run,
    infer_run_status,
    content_hash,
)


def validate_start_run(requirement_key: str, batch_id: str) -> None:
    """Check that the batch and requirement exist without creating a run.

    Raises ValueError with a user-facing message on failure.
    """
    batch = get_batch(batch_id)
    if batch is None:
        raise ValueError(f"Import batch '{batch_id}' not found")
    req = _find_requirement(batch["requirements"], requirement_key)
    if req is None:
        raise ValueError(
            f"Requirement '{requirement_key}' not found in batch '{batch_id}'"
        )


def start_run(requirement_key: str, batch_id: str) -> dict[str, Any]:
    """Create an Active Run for one Requirement.

    Writes 00_requirements.json, runs prepare_clarification_review,
    and returns run info.
    """
    batch = get_batch(batch_id)
    if batch is None:
        raise ValueError(f"Import batch '{batch_id}' not found")

    req = _find_requirement(batch["requirements"], requirement_key)
    if req is None:
        raise ValueError(
            f"Requirement '{requirement_key}' not found in batch '{batch_id}'"
        )

    run_dir = make_run_dir(requirement_key, req.get("description", ""))
    write_run_input(run_dir, req)

    settings = get_settings()
    provider = create_provider(settings)

    input_path = str(run_dir / "00_requirements.json")
    review = prepare_clarification_review(
        input_path=input_path,
        out_dir=str(run_dir),
        provider=provider,
    )

    return get_run(run_dir.name) or {"run_dir": run_dir.name, "requirement_key": requirement_key}


def load_clarification_review(run_dir_name: str) -> dict[str, Any] | None:
    """Load the clarification review artifact for the workbench."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        return None

    run_path = Path(run_info["run_path"])
    review_path = run_path / "clarification_review.json"
    if not review_path.exists():
        return None

    data = read_json(review_path)
    return {
        "run": run_info,
        "review": data,
    }


def save_clarification_draft(run_dir_name: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """Save draft decisions without validation."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        raise ValueError(f"Run '{run_dir_name}' not found")

    run_path = Path(run_info["run_path"])
    review_path = run_path / "clarification_review.json"
    if not review_path.exists():
        raise ValueError("Clarification review artifact not found")

    data = read_json(review_path)

    # Update decisions
    dec_by_id = {d["item_id"]: d for d in decisions}
    for existing in data.get("decisions", []):
        update = dec_by_id.get(existing["item_id"])
        if update is not None:
            existing["decision"] = update.get("decision", existing.get("decision", ""))
            existing["reason_codes"] = update.get("reason_codes", existing.get("reason_codes", []))
            existing["reason_text"] = update.get("reason_text", existing.get("reason_text", ""))
            existing["clarified_value"] = update.get("clarified_value", existing.get("clarified_value", ""))
            existing["edited_content"] = update.get("edited_content", existing.get("edited_content", {}))

    write_json(review_path, data)

    return {
        "saved": True,
        "run": get_run(run_dir_name),
        "hash": content_hash(data),
    }


def save_and_advance_clarification(run_dir_name: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """Save clarification decisions, validate, produce clarified test basis,
    and prepare case intent review.

    If the decisions hash is unchanged and the downstream artifact already
    exists, reuses it instead of rerunning LLM stages.
    Returns validation errors or success with updated run info.
    """
    # First save
    save_result = save_clarification_draft(run_dir_name, decisions)
    run_info = get_run(run_dir_name)
    assert run_info is not None
    run_path = Path(run_info["run_path"])

    # Unchanged-upstream reuse: if decisions hash matches and downstream exists, skip
    dec_hash = content_hash(decisions if isinstance(decisions, list) else [])
    state_path = run_path / "_advance_state.json"
    downstream = run_path / "case_intent_review.json"
    if state_path.exists() and downstream.exists():
        try:
            state = read_json(state_path)
            if state.get("clarification_decisions_hash") == dec_hash:
                return {
                    "saved": True,
                    "reused": True,
                    "validated": True,
                    "blocked": False,
                    "advanced_to": "intent_ready",
                    "run": get_run(run_dir_name),
                }
        except Exception:
            pass

    # Validate
    review_path = str(run_path / "clarification_review.json")
    validation, basis = validate_clarification_review(review_path)

    if not validation.is_valid:
        return {
            "saved": True,
            "validated": False,
            "status": "validation_failed",
            "errors": [_validation_error_to_dict(e) for e in validation.errors],
            "run": run_info,
        }

    # Check for blocked
    assert basis is not None
    if basis.blocked:
        return {
            "saved": True,
            "validated": True,
            "blocked": True,
            "status": "blocked",
            "block_reasons": basis.block_reasons,
            "run": get_run(run_dir_name),
        }

    # Prepare case intent review
    settings = get_settings()
    provider = create_provider(settings)
    from ..review_pipeline.stages.plan_case_intents import prepare_intent_review
    prepare_intent_review(str(run_path), provider=provider, memory_hints=None)

    # Persist decisions hash for future reuse checks
    _persist_advance_state(run_path, "clarification_decisions_hash", dec_hash)

    return {
        "saved": True,
        "validated": True,
        "blocked": False,
        "advanced_to": "intent_ready",
        "run": get_run(run_dir_name),
    }


# ── Case Intent Review ────────────────────────────────────────────────────


def load_intent_review(run_dir_name: str) -> dict[str, Any] | None:
    """Load the case intent review artifact for editing."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        return None
    run_path = Path(run_info["run_path"])
    review_path = run_path / "case_intent_review.json"
    if not review_path.exists():
        return None
    data = read_json(review_path)
    return {"run": run_info, "review": data}


def save_intent_draft(run_dir_name: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """Save draft case intent decisions without validation."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        raise ValueError(f"Run '{run_dir_name}' not found")
    run_path = Path(run_info["run_path"])
    review_path = run_path / "case_intent_review.json"
    if not review_path.exists():
        raise ValueError("Case intent review artifact not found")

    data = read_json(review_path)
    dec_by_id = {d["intent_id"]: d for d in decisions}
    for existing in data.get("decisions", []):
        update = dec_by_id.get(existing["intent_id"])
        if update is not None:
            existing["decision"] = update.get("decision", existing.get("decision", ""))
            existing["reason_codes"] = update.get("reason_codes", existing.get("reason_codes", []))
            existing["reason_text"] = update.get("reason_text", existing.get("reason_text", ""))
            existing["revised_intent_text"] = update.get("revised_intent_text", existing.get("revised_intent_text", ""))
            existing["merge_target_id"] = update.get("merge_target_id", existing.get("merge_target_id", ""))
            existing["split_children"] = update.get("split_children", existing.get("split_children", []))

    write_json(review_path, data)
    return {"saved": True, "run": get_run(run_dir_name), "hash": content_hash(data)}


def save_and_generate_cases(run_dir_name: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """Save intent decisions, validate, produce ApprovedCasePlan,
    generate cases, evaluate, and return results.

    If decisions hash is unchanged and generated_cases.json exists, reuses it.
    """
    save_result = save_intent_draft(run_dir_name, decisions)
    run_info = get_run(run_dir_name)
    assert run_info is not None
    run_path = Path(run_info["run_path"])

    # Unchanged-upstream reuse
    dec_hash = content_hash(decisions if isinstance(decisions, list) else [])
    state_path = run_path / "_advance_state.json"
    downstream = run_path / "generated_cases.json"
    if state_path.exists() and downstream.exists():
        try:
            state = read_json(state_path)
            if state.get("intent_decisions_hash") == dec_hash:
                return {
                    "saved": True,
                    "reused": True,
                    "validated": True,
                    "generated": True,
                    "evaluated": True,
                    "case_count": len(read_json(downstream)),
                    "run": get_run(run_dir_name),
                }
        except Exception:
            pass

    # Validate intent review
    from ..review_pipeline.stages.validate_case_intent import validate_case_intent_review
    review_path = str(run_path / "case_intent_review.json")
    validation, plan = validate_case_intent_review(review_path)

    if not validation.is_valid:
        return {
            "saved": True,
            "validated": False,
            "status": "validation_failed",
            "errors": [_validation_error_to_dict(e) for e in validation.errors],
            "run": run_info,
        }

    assert plan is not None

    # Generate cases
    settings = get_settings()
    provider = create_provider(settings)
    from ..review_pipeline.stages.write_cases import generate_cases
    case_set = generate_cases(str(run_path), provider=provider)

    # Evaluate
    from ..review_pipeline.stages.evaluate import evaluate_run
    evaluate_run(str(run_path))

    # Persist decisions hash for future reuse checks
    _persist_advance_state(run_path, "intent_decisions_hash", dec_hash)

    return {
        "saved": True,
        "validated": True,
        "generated": True,
        "evaluated": True,
        "case_count": len(case_set.cases),
        "approved_intent_count": len(plan.approved_intents),
        "run": get_run(run_dir_name),
    }


def _persist_advance_state(run_path: Path, key: str, hash_value: str) -> None:
    state_path = run_path / "_advance_state.json"
    state: dict[str, Any] = {}
    if state_path.exists():
        try:
            state = read_json(state_path)
        except Exception:
            pass
    state[key] = hash_value
    write_json(state_path, state)


def _find_requirement(requirements: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    for r in requirements:
        if r.get("requirement_key") == key:
            return r
    return None


def _validation_error_to_dict(e: ValidationError) -> dict[str, Any]:
    return {
        "artifact_path": e.artifact_path,
        "field_path": e.field_path,
        "message": e.message,
    }
