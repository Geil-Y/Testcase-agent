"""Review Workbench — Console bridge to the simplified A/B/C reviewed pipeline.

Stage labels: extraction / case intents / case generation / case review.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..provider.factory import create_provider
from ..review_pipeline.artifacts.io import read_json, write_json
from ..review_pipeline.artifacts.models import (
    ExtractedTestBasis,
    CaseIntentSet,
    ExtractionReviewAction,
    IntentReviewAction,
    RegenerateRequest,
)
from ..review_pipeline.artifacts.validation import (
    ValidationError,
    ValidationResult,
    is_legacy_run_dir,
    get_legacy_unsupported_message,
    validate_reviewed_artifact,
)
from ..review_pipeline.stages.extract_test_basis import extract_test_basis, accept_extraction
from .imports import get_batch
from .runs import (
    make_run_dir,
    write_run_input,
    get_run,
    content_hash,
)
from .trace import write_trace_event


# ═══════════════════════════════════════════════════════════════════════════════
# Start run: LLM-A extraction
# ═══════════════════════════════════════════════════════════════════════════════

def validate_start_run(requirement_key: str, batch_id: str) -> None:
    """Check that the batch and requirement exist without creating a run."""
    batch = get_batch(batch_id)
    if batch is None:
        raise ValueError(f"Import batch '{batch_id}' not found")
    req = _find_requirement(batch["requirements"], requirement_key)
    if req is None:
        raise ValueError(
            f"Requirement '{requirement_key}' not found in batch '{batch_id}'"
        )


def start_run(requirement_key: str, batch_id: str) -> dict[str, Any]:
    """Create an Active Run, run LLM-A extraction, and return run info."""
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
    provider_name = settings.llm.provider
    model_name = settings.llm.model_name

    write_trace_event(run_dir, stage="extraction", event="stage_started",
                      message="Starting test basis extraction")

    t0 = time.time()
    input_path = str(run_dir / "00_requirements.json")
    basis = extract_test_basis(
        input_path=input_path,
        out_dir=str(run_dir),
        provider=provider,
    )
    dt_ms = round((time.time() - t0) * 1000, 1)

    write_trace_event(run_dir, stage="extraction", event="llm_done",
                      provider=provider_name, model=model_name,
                      duration_ms=dt_ms,
                      message="Test basis extraction complete")
    write_trace_event(run_dir, stage="extraction", event="artifact_written",
                      message="Written extracted_test_basis.json")
    write_trace_event(run_dir, stage="extraction", event="completed",
                      message="Extraction complete")

    return get_run(run_dir.name) or {"run_dir": run_dir.name, "requirement_key": requirement_key}


# ═══════════════════════════════════════════════════════════════════════════════
# Extraction review
# ═══════════════════════════════════════════════════════════════════════════════

def load_extraction(run_dir_name: str) -> dict[str, Any] | None:
    """Load the extracted test basis for review."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        return None

    run_path = Path(run_info["run_path"])

    # Legacy detection
    if is_legacy_run_dir(run_path):
        return {
            "run": run_info,
            "legacy": True,
            "message": get_legacy_unsupported_message(run_path),
        }

    basis_path = run_path / "extracted_test_basis.json"
    if not basis_path.exists():
        return None

    data = read_json(basis_path)

    # Check if already reviewed
    reviewed_path = run_path / "reviewed_extracted_test_basis.json"
    reviewed = reviewed_path.exists()

    return {
        "run": run_info,
        "extraction": data,
        "reviewed": reviewed,
    }


def save_extraction_review(
    run_dir_name: str,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Save extraction review actions, producing reviewed_extracted_test_basis.json."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        raise ValueError(f"Run '{run_dir_name}' not found")

    run_path = Path(run_info["run_path"])

    if is_legacy_run_dir(run_path):
        raise ValueError(get_legacy_unsupported_message(run_path))

    parsed_actions = [ExtractionReviewAction(**a) for a in actions]
    from ..review_pipeline.stages.extract_test_basis import apply_extraction_review
    basis = apply_extraction_review(run_path, parsed_actions)

    return {
        "saved": True,
        "reviewed": True,
        "run": get_run(run_dir_name),
        "item_count": sum(len(v) for v in basis.sections.values()),
        "blocking_gaps": basis.blocking_gaps,
    }


def accept_extraction_all(run_dir_name: str) -> dict[str, Any]:
    """Accept All: write reviewed_extracted_test_basis.json."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        raise ValueError(f"Run '{run_dir_name}' not found")

    run_path = Path(run_info["run_path"])

    if is_legacy_run_dir(run_path):
        raise ValueError(get_legacy_unsupported_message(run_path))

    basis = accept_extraction(run_path)
    return {
        "saved": True,
        "reviewed": True,
        "run": get_run(run_dir_name),
        "item_count": sum(len(v) for v in basis.sections.values()),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Intent planning (LLM-B)
# ═══════════════════════════════════════════════════════════════════════════════

def load_intents(run_dir_name: str) -> dict[str, Any] | None:
    """Load the case intents for review."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        return None

    run_path = Path(run_info["run_path"])

    if is_legacy_run_dir(run_path):
        return {
            "run": run_info,
            "legacy": True,
            "message": get_legacy_unsupported_message(run_path),
        }

    intents_path = run_path / "case_intents.json"
    if not intents_path.exists():
        return None

    data = read_json(intents_path)
    reviewed_path = run_path / "reviewed_case_intents.json"
    reviewed = reviewed_path.exists()

    return {
        "run": run_info,
        "intents": data,
        "reviewed": reviewed,
    }


def plan_and_load_intents(run_dir_name: str) -> dict[str, Any]:
    """Run LLM-B and return intents for review."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        raise ValueError(f"Run '{run_dir_name}' not found")

    run_path = Path(run_info["run_path"])

    if is_legacy_run_dir(run_path):
        raise ValueError(get_legacy_unsupported_message(run_path))

    settings = get_settings()
    provider = create_provider(settings)

    write_trace_event(run_path, stage="case_intents", event="stage_started",
                      message="Planning case intents")

    t0 = time.time()
    from ..review_pipeline.stages.plan_case_intents import plan_intents
    intent_set = plan_intents(run_path, provider=provider)
    dt_ms = round((time.time() - t0) * 1000, 1)

    write_trace_event(run_path, stage="case_intents", event="llm_done",
                      duration_ms=dt_ms,
                      message=f"Planned {len(intent_set.intents)} intents")
    write_trace_event(run_path, stage="case_intents", event="artifact_written",
                      message="Written case_intents.json")
    write_trace_event(run_path, stage="case_intents", event="completed",
                      message="Intent planning complete")

    data = read_json(run_path / "case_intents.json")
    return {
        "run": get_run(run_dir_name),
        "intents": data,
        "reviewed": False,
    }


def save_intent_review(
    run_dir_name: str,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Save intent review actions, producing reviewed_case_intents.json."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        raise ValueError(f"Run '{run_dir_name}' not found")

    run_path = Path(run_info["run_path"])

    if is_legacy_run_dir(run_path):
        raise ValueError(get_legacy_unsupported_message(run_path))

    parsed_actions = [IntentReviewAction(**a) for a in actions]
    from ..review_pipeline.stages.plan_case_intents import apply_intent_review
    intent_set = apply_intent_review(run_path, parsed_actions)

    return {
        "saved": True,
        "reviewed": True,
        "run": get_run(run_dir_name),
        "intent_count": len(intent_set.intents),
        "blocking_gaps": intent_set.blocking_gaps,
    }


def accept_intents_all(run_dir_name: str) -> dict[str, Any]:
    """Accept All: write reviewed_case_intents.json."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        raise ValueError(f"Run '{run_dir_name}' not found")

    run_path = Path(run_info["run_path"])

    if is_legacy_run_dir(run_path):
        raise ValueError(get_legacy_unsupported_message(run_path))

    from ..review_pipeline.stages.plan_case_intents import accept_intents
    intent_set = accept_intents(run_path)
    return {
        "saved": True,
        "reviewed": True,
        "run": get_run(run_dir_name),
        "intent_count": len(intent_set.intents),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Case generation (LLM-C)
# ═══════════════════════════════════════════════════════════════════════════════

def load_cases(run_dir_name: str) -> dict[str, Any] | None:
    """Load generated cases (or reviewed cases if available)."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        return None

    run_path = Path(run_info["run_path"])

    if is_legacy_run_dir(run_path):
        return {
            "run": run_info,
            "legacy": True,
            "message": get_legacy_unsupported_message(run_path),
        }

    reviewed_path = run_path / "reviewed_cases.json"
    generated_path = run_path / "generated_cases.json"

    if reviewed_path.exists():
        data = read_json(reviewed_path)
        return {
            "run": run_info,
            "cases": data,
            "reviewed": True,
        }
    elif generated_path.exists():
        data = read_json(generated_path)
        return {
            "run": run_info,
            "cases": data,
            "reviewed": False,
            "pending_review": True,
        }

    return None


def generate_and_load_cases(run_dir_name: str) -> dict[str, Any]:
    """Run LLM-C and return generated cases."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        raise ValueError(f"Run '{run_dir_name}' not found")

    run_path = Path(run_info["run_path"])

    if is_legacy_run_dir(run_path):
        raise ValueError(get_legacy_unsupported_message(run_path))

    settings = get_settings()
    provider = create_provider(settings)

    write_trace_event(run_path, stage="case_generation", event="stage_started",
                      message="Generating test cases")

    t0 = time.time()
    from ..review_pipeline.stages.write_cases import generate_cases
    case_set = generate_cases(run_path, provider=provider)
    dt_ms = round((time.time() - t0) * 1000, 1)

    write_trace_event(run_path, stage="case_generation", event="llm_done",
                      duration_ms=dt_ms,
                      message=f"Generated {len(case_set.cases)} case(s)")
    write_trace_event(run_path, stage="case_generation", event="artifact_written",
                      message="Written generated_cases.json")
    write_trace_event(run_path, stage="case_generation", event="completed",
                      message="Case generation complete")

    data = read_json(run_path / "generated_cases.json")
    return {
        "run": get_run(run_dir_name),
        "cases": data,
        "reviewed": False,
        "pending_review": True,
    }


def accept_cases_all(run_dir_name: str) -> dict[str, Any]:
    """Accept All: write reviewed_cases.json."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        raise ValueError(f"Run '{run_dir_name}' not found")

    run_path = Path(run_info["run_path"])

    if is_legacy_run_dir(run_path):
        raise ValueError(get_legacy_unsupported_message(run_path))

    from ..review_pipeline.stages.write_cases import accept_cases
    case_set = accept_cases(run_path)
    return {
        "saved": True,
        "reviewed": True,
        "run": get_run(run_dir_name),
        "case_count": len(case_set.cases),
    }


def save_case_edit(run_dir_name: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Save manually edited cases as reviewed_cases.json."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        raise ValueError(f"Run '{run_dir_name}' not found")

    run_path = Path(run_info["run_path"])

    if is_legacy_run_dir(run_path):
        raise ValueError(get_legacy_unsupported_message(run_path))

    from ..review_pipeline.stages.write_cases import edit_cases
    case_set = edit_cases(run_path, cases)
    return {
        "saved": True,
        "reviewed": True,
        "run": get_run(run_dir_name),
        "case_count": len(case_set.cases),
    }


def regenerate_cases(
    run_dir_name: str,
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    """Regenerate cases with review comments."""
    run_info = get_run(run_dir_name)
    if run_info is None:
        raise ValueError(f"Run '{run_dir_name}' not found")

    run_path = Path(run_info["run_path"])

    if is_legacy_run_dir(run_path):
        raise ValueError(get_legacy_unsupported_message(run_path))

    settings = get_settings()
    provider = create_provider(settings)

    from ..review_pipeline.stages.write_cases import regenerate_and_save

    parsed = [RegenerateRequest(**r) for r in requests]
    case_set = regenerate_and_save(run_path, parsed, provider=provider)

    return {
        "saved": True,
        "regenerated": True,
        "reviewed": True,
        "run": get_run(run_dir_name),
        "case_count": len(case_set.cases),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy compatibility aliases — only for test backward compatibility.
# New code must use the functions above, NOT these aliases.
# ═══════════════════════════════════════════════════════════════════════════════

def load_clarification_review(run_dir_name: str) -> dict[str, Any] | None:
    """[LEGACY ALIAS] Use load_extraction() instead."""
    return load_extraction(run_dir_name)


def load_intent_review(run_dir_name: str) -> dict[str, Any] | None:
    """[LEGACY ALIAS] Use load_intents() instead."""
    return load_intents(run_dir_name)


def save_clarification_draft(run_dir_name: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """[LEGACY ALIAS] Use save_extraction_review() instead."""
    return save_extraction_review(run_dir_name, decisions)


def save_intent_draft(run_dir_name: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """[LEGACY ALIAS] Use save_intent_review() instead."""
    return save_intent_review(run_dir_name, decisions)


def save_and_advance_clarification(run_dir_name: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """[LEGACY ALIAS] Accept extraction review, plan intents, return result."""
    result = save_extraction_review(run_dir_name, decisions)
    if not result.get("saved"):
        return result
    return plan_and_load_intents(run_dir_name)


def save_and_generate_cases(run_dir_name: str, decisions: list[dict[str, Any]]) -> dict[str, Any]:
    """[LEGACY ALIAS] Save intent review, generate cases, return result."""
    result = save_intent_review(run_dir_name, decisions)
    if not result.get("saved"):
        return result
    return generate_and_load_cases(run_dir_name)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _find_requirement(requirements: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    for r in requirements:
        if r.get("requirement_key") == key:
            return r
    return None
