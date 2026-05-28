"""LLM-B: Case Intent Planner stage.

Reads the requirement description and ``reviewed_extracted_test_basis.json``.
Plans coverage dimensions and case intents. Does NOT extract new evidence or
discover new missing information.

Writes ``case_intents.json``. Accept All or human review writes
``reviewed_case_intents.json`` using the same schema.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from testcase_agent.review_pipeline.artifacts.io import read_json, write_json
from testcase_agent.review_pipeline.artifacts.models import (
    ExtractedTestBasis,
    CaseIntentSet,
    CaseIntentItem,
    IntentReviewAction,
)
from testcase_agent.review_pipeline.artifacts.formatting import (
    parse_json_response,
    dump_raw_response,
    format_known_items,
    format_unresolved_items,
)
from testcase_agent.review_pipeline.artifacts.validation import (
    ValidationResult,
    validate_reviewed_artifact,
    validate_accept_all_no_blocking_gaps,
)
from testcase_agent.review_pipeline.prompts import render_prompt


# ── Stage: Plan case intents ──────────────────────────────────────────────────

def plan_intents(run_dir: str | Path, *, provider=None) -> CaseIntentSet:
    """Run LLM-B intent planning.

    Reads ``reviewed_extracted_test_basis.json`` from run_dir.
    Writes ``case_intents.json``.
    """
    rdir = Path(run_dir)

    reviewed_path = rdir / "reviewed_extracted_test_basis.json"
    validation = validate_reviewed_artifact(
        reviewed_path, artifact_label="reviewed_extracted_test_basis.json")
    if not validation.is_valid:
        raise ValueError(
            f"Cannot plan intents: {validation.format_errors()}")

    basis = ExtractedTestBasis(**read_json(reviewed_path))

    # Blocking gaps prevent planning
    if basis.has_blocking_gaps:
        intent_set = CaseIntentSet(
            requirement_key=basis.requirement_key,
            source_description=basis.source_description,
            intents=[],
            blocking_gaps=list(basis.blocking_gaps),
        )
        write_json(rdir / "case_intents.json", intent_set.model_dump())
        return intent_set

    if provider is None:
        intent_set = _plan_placeholder(basis)
    else:
        intent_set = _call_plan_llm(basis, provider, rdir)

    write_json(rdir / "case_intents.json", intent_set.model_dump())
    return intent_set


# ── Review: Accept All ─────────────────────────────────────────────────────────

def accept_intents(run_dir: str | Path) -> CaseIntentSet:
    """Accept All: copy case_intents.json to reviewed_case_intents.json."""
    rdir = Path(run_dir)
    src = rdir / "case_intents.json"
    dst = rdir / "reviewed_case_intents.json"

    if not src.exists():
        raise ValueError("case_intents.json not found — run intent planning first.")

    validation = validate_accept_all_no_blocking_gaps(src, artifact_label="case_intents.json")
    if not validation.is_valid:
        raise ValueError(f"Cannot Accept All: {validation.format_errors()}")

    data = read_json(src)
    write_json(dst, data)
    return CaseIntentSet(**data)


# ── Review: Apply review actions ───────────────────────────────────────────────

def apply_intent_review(
    run_dir: str | Path,
    actions: list[IntentReviewAction],
) -> CaseIntentSet:
    """Apply human review actions to case_intents.json and write reviewed version."""
    rdir = Path(run_dir)
    src = rdir / "case_intents.json"
    if not src.exists():
        raise ValueError("case_intents.json not found — run intent planning first.")

    intent_set = CaseIntentSet(**read_json(src))

    for action in actions:
        if action.action == "accept":
            pass  # keep as-is
        elif action.action == "edit":
            _intent_edit(intent_set, action)
        elif action.action == "add":
            _intent_add(intent_set, action)
        elif action.action == "remove":
            _intent_remove(intent_set, action)
        elif action.action == "block":
            _intent_block(intent_set, action)

    write_json(rdir / "reviewed_case_intents.json", intent_set.model_dump())
    return intent_set


def _intent_edit(intent_set: CaseIntentSet, action: IntentReviewAction) -> None:
    _intent_remove(intent_set, action)
    if action.edited_intent is not None:
        intent_set.intents.append(action.edited_intent)


def _intent_add(intent_set: CaseIntentSet, action: IntentReviewAction) -> None:
    if action.new_intent is not None:
        intent_set.intents.append(action.new_intent)


def _intent_remove(intent_set: CaseIntentSet, action: IntentReviewAction) -> None:
    intent_set.intents = [i for i in intent_set.intents if i.intent_id != action.intent_id]


def _intent_block(intent_set: CaseIntentSet, action: IntentReviewAction) -> None:
    if action.new_intent is not None and action.new_intent.intent_text:
        intent_set.blocking_gaps.append(action.new_intent.intent_text)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _call_plan_llm(
    basis: ExtractedTestBasis, provider, run_dir: Path
) -> CaseIntentSet:
    """Call LLM-B and parse its JSON response."""
    description = basis.source_description

    # Build prompt sections from reviewed extraction
    known_signals = format_known_items(basis, "signals")
    known_thresholds = format_known_items(basis, "thresholds")
    known_timing = format_known_items(basis, "timing")
    known_states = format_known_items(basis, "states")
    known_observations = format_known_items(basis, "observations")
    unresolved_items = format_unresolved_items(basis)

    system_prompt, user_prompt = render_prompt(
        "plan_intents",
        requirement_key=basis.requirement_key,
        description=description,
        known_signals=known_signals,
        known_thresholds=known_thresholds,
        known_timing=known_timing,
        known_states=known_states,
        known_observations=known_observations,
        unresolved_items=unresolved_items,
        # supplementary_info intentionally NOT passed
    )
    raw_response = provider.complete(system_prompt, user_prompt)

    try:
        payload = parse_json_response(raw_response)
        return CaseIntentSet(**payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        dump_raw_response(run_dir, raw_response, "llm_b")
        raise ValueError(f"LLM-B response was not valid JSON: {exc}") from exc


def _plan_placeholder(basis: ExtractedTestBasis) -> CaseIntentSet:
    """Placeholder intent planning for testing without a real LLM."""
    return CaseIntentSet(
        requirement_key=basis.requirement_key,
        source_description=basis.source_description,
        intents=[
            CaseIntentItem(
                intent_id="intent-1",
                coverage_dimension="normal_behavior",
                intent_text=f"Verify normal operation of {basis.requirement_key}",
            ),
        ],
        blocking_gaps=[],
    )


# ── Legacy aliases (for test backward compatibility) ────────────────────────

def prepare_intent_review(run_dir: str, *, provider=None, memory_hints: dict | None = None) -> CaseIntentSet:
    """[LEGACY ALIAS] Use plan_intents() instead. Reads reviewed_extracted_test_basis.json."""
    return plan_intents(run_dir, provider=provider)
