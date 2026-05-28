"""LLM-C: Case Writer stage.

Reads ``reviewed_extracted_test_basis.json`` and ``reviewed_case_intents.json``.
Generates one test case per approved intent using legacy-style known sections
and unresolved missing items. Does NOT discover new missing information.

Writes ``generated_cases.json``.
Accept All / Edit writes ``reviewed_cases.json``.
Regenerate re-runs LLM-C for a single intent with a review comment.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from testcase_agent.review_pipeline.artifacts.io import read_json, write_json
from testcase_agent.review_pipeline.artifacts.models import (
    ExtractedTestBasis,
    CaseIntentSet,
    CaseIntentItem,
    GeneratedCase,
    GeneratedCaseSet,
    RegenerateRequest,
)
from testcase_agent.review_pipeline.artifacts.validation import (
    validate_reviewed_artifact,
    validate_accept_all_no_blocking_gaps,
)
from testcase_agent.review_pipeline.prompts import render_prompt


# ── Stage: Generate cases ──────────────────────────────────────────────────────

def generate_cases(run_dir: str | Path, *, provider=None) -> GeneratedCaseSet:
    """Generate test cases from reviewed extraction and reviewed intents.

    Reads ``reviewed_extracted_test_basis.json`` and ``reviewed_case_intents.json``.
    Generates exactly one case per approved intent.
    Writes ``generated_cases.json``.
    """
    rdir = Path(run_dir)

    # Validate reviewed artifacts exist
    for art_name in ["reviewed_extracted_test_basis.json", "reviewed_case_intents.json"]:
        validation = validate_reviewed_artifact(
            rdir / art_name, artifact_label=art_name)
        if not validation.is_valid:
            raise ValueError(f"Cannot generate cases: {validation.format_errors()}")

    basis = ExtractedTestBasis(**read_json(rdir / "reviewed_extracted_test_basis.json"))
    intents = CaseIntentSet(**read_json(rdir / "reviewed_case_intents.json"))

    # Block if upstream has blocking gaps
    if basis.has_blocking_gaps or intents.has_blocking_gaps:
        gaps = list(basis.blocking_gaps) + list(intents.blocking_gaps)
        raise ValueError(
            f"Cannot generate cases: upstream blocking gaps present: {'; '.join(gaps)}")

    cases: list[GeneratedCase] = []
    for intent in intents.intents:
        if provider is None:
            case = _write_placeholder(basis, intent)
        else:
            case = _call_write_case_llm(basis, intent, provider, rdir)
        cases.append(case)

    case_set = GeneratedCaseSet(
        requirement_key=basis.requirement_key,
        source_description=basis.source_description,
        cases=cases,
    )

    write_json(rdir / "generated_cases.json", case_set.model_dump())

    return case_set


# ── Review: Accept All ─────────────────────────────────────────────────────────

def accept_cases(run_dir: str | Path) -> GeneratedCaseSet:
    """Accept All: copy generated_cases.json to reviewed_cases.json.

    Both files use the same GeneratedCaseSet schema (object with ``cases`` list).
    """
    rdir = Path(run_dir)
    src = rdir / "generated_cases.json"
    dst = rdir / "reviewed_cases.json"

    if not src.exists():
        raise ValueError("generated_cases.json not found — run case generation first.")

    data = read_json(src)
    write_json(dst, data)
    return GeneratedCaseSet(**data)


# ── Review: Edit cases ─────────────────────────────────────────────────────────

def edit_cases(run_dir: str | Path, cases: list[dict[str, Any]]) -> GeneratedCaseSet:
    """Save manually edited cases as reviewed_cases.json. Same schema as generated."""
    rdir = Path(run_dir)
    src = rdir / "generated_cases.json"

    key = ""
    desc = ""
    if src.exists():
        try:
            existing = read_json(src)
            if isinstance(existing, dict):
                key = existing.get("requirement_key", "")
                desc = existing.get("source_description", "")
        except Exception:
            pass

    # Fallback: get key/desc from reviewed extraction
    if not key:
        try:
            basis_data = read_json(rdir / "reviewed_extracted_test_basis.json")
            key = basis_data.get("requirement_key", "")
            desc = basis_data.get("source_description", "")
        except Exception:
            pass

    case_set_data = {
        "requirement_key": key,
        "source_description": desc,
        "cases": cases,
    }
    write_json(rdir / "reviewed_cases.json", case_set_data)
    return GeneratedCaseSet(**case_set_data)


# ── Regenerate ─────────────────────────────────────────────────────────────────

def regenerate_case(
    run_dir: str | Path,
    request: RegenerateRequest,
    *,
    provider=None,
) -> GeneratedCase:
    """Regenerate a single case using reviewed artifacts + a review comment.

    Inputs must be reviewed artifacts only. The review comment can guide
    wording, structure, and use of approved materials, but must not introduce
    new concrete identifiers, thresholds, timing, states, observations,
    or new case intents.
    """
    rdir = Path(run_dir)

    # Validate reviewed artifacts
    for art_name in ["reviewed_extracted_test_basis.json", "reviewed_case_intents.json"]:
        validation = validate_reviewed_artifact(
            rdir / art_name, artifact_label=art_name)
        if not validation.is_valid:
            raise ValueError(f"Cannot regenerate: {validation.format_errors()}")

    basis = ExtractedTestBasis(**read_json(rdir / "reviewed_extracted_test_basis.json"))
    intents = CaseIntentSet(**read_json(rdir / "reviewed_case_intents.json"))

    # Find the intent
    intent = _find_intent(intents, request.intent_id)
    if intent is None:
        raise ValueError(
            f"Intent {request.intent_id} not found in reviewed_case_intents.json")

    if provider is None:
        case = _write_placeholder(basis, intent)
        case.case_id = request.case_id
        return case

    case = _call_write_case_llm(
        basis, intent, provider, rdir,
        review_comment=request.review_comment,
    )
    case.case_id = request.case_id

    return case


def regenerate_and_save(
    run_dir: str | Path,
    requests: list[RegenerateRequest],
    *,
    provider=None,
) -> GeneratedCaseSet:
    """Regenerate cases and save to reviewed_cases.json."""
    rdir = Path(run_dir)
    cases: list[GeneratedCase] = []

    for req in requests:
        case = regenerate_case(run_dir, req, provider=provider)
        cases.append(case)

    # Read existing reviewed cases (if any) and merge
    existing_ids: set[str] = set()
    reviewed_path = rdir / "reviewed_cases.json"
    if reviewed_path.exists():
        try:
            existing_data = read_json(reviewed_path)
            existing_cases = existing_data.get("cases", [])
            for c in existing_cases:
                cid = c.get("case_id", "")
                if cid not in {r.case_id for r in requests}:
                    cases_data = {
                        "case_id": cid,
                        "title": c.get("title", ""),
                        "objective": c.get("objective", ""),
                        "pre_condition": c.get("pre_condition", ""),
                        "steps": c.get("steps", []),
                        "post_condition": c.get("post_condition", ""),
                        "requirement_key": c.get("requirement_key", ""),
                        "intent_id": c.get("intent_id", ""),
                        "coverage_dimension": c.get("coverage_dimension", ""),
                    }
                    cases.append(GeneratedCase(**cases_data))
        except Exception:
            pass

    basis = ExtractedTestBasis(**read_json(rdir / "reviewed_extracted_test_basis.json"))
    case_set = GeneratedCaseSet(
        requirement_key=basis.requirement_key,
        source_description=basis.source_description,
        cases=cases,
    )
    write_json(rdir / "reviewed_cases.json", case_set.model_dump())
    return case_set


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _call_write_case_llm(
    basis: ExtractedTestBasis,
    intent: CaseIntentItem,
    provider,
    run_dir: Path,
    *,
    review_comment: str = "",
) -> GeneratedCase:
    """Call LLM-C and parse its JSON response."""
    description = basis.source_description

    known_signals = _format_known_items(basis, "signals")
    known_thresholds = _format_known_items(basis, "thresholds")
    known_timing = _format_known_items(basis, "timing")
    known_states = _format_known_items(basis, "states")
    known_observations = _format_known_items(basis, "observations")
    unresolved_items = _format_unresolved_items(basis)

    system_prompt, user_prompt = render_prompt(
        "write_case",
        requirement_key=basis.requirement_key,
        description=description,
        intent_id=intent.intent_id,
        coverage_dimension=intent.coverage_dimension,
        intent_text=intent.intent_text,
        known_signals=known_signals,
        known_thresholds=known_thresholds,
        known_timing=known_timing,
        known_states=known_states,
        known_observations=known_observations,
        unresolved_items=unresolved_items,
        review_comment=review_comment,
        # supplementary_info intentionally NOT passed
    )
    raw_response = provider.complete(system_prompt, user_prompt)

    try:
        payload = _parse_json_response(raw_response)
        payload.setdefault("case_id", f"case-{uuid.uuid4().hex[:8]}")
        payload.setdefault("requirement_key", basis.requirement_key)
        payload.setdefault("intent_id", intent.intent_id)
        payload.setdefault("coverage_dimension", intent.coverage_dimension)
        # Coerce step_number to string (LLM may emit int)
        for step in payload.get("steps", []):
            if "step_number" in step:
                step["step_number"] = str(step["step_number"])
        return GeneratedCase(**payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        _dump_raw_response(run_dir, raw_response, "llm_c")
        raise ValueError(f"LLM-C response was not valid JSON: {exc}") from exc


def _write_placeholder(basis: ExtractedTestBasis, intent: CaseIntentItem) -> GeneratedCase:
    """Placeholder case for testing without a real LLM."""
    return GeneratedCase(
        case_id=f"case-{uuid.uuid4().hex[:8]}",
        title=intent.intent_text,
        objective=f"Verify {intent.coverage_dimension} behavior",
        pre_condition="BMS initialized, all parameters within normal operating range, no active faults.",
        steps=[
            {"step_number": "1", "action": "Set up test conditions per requirement",
             "expected_result": "System responds correctly"},
            {"step_number": "2", "action": "Execute verification step",
             "expected_result": "Behavior matches specification"},
        ],
        post_condition="System returned to normal operating state.",
        requirement_key=basis.requirement_key,
        intent_id=intent.intent_id,
        coverage_dimension=intent.coverage_dimension,
    )


def _format_known_items(basis: ExtractedTestBasis, section: str) -> str:
    items = basis.known_items(section)
    if not items:
        return ""
    return "\n".join(f"- [{it.item_id}] {it.content}" for it in items)


def _format_unresolved_items(basis: ExtractedTestBasis) -> str:
    items = basis.all_needs_review_items()
    if not items:
        return ""
    return "\n".join(f"- [{it.item_id}] {it.need}" for it in items)


def _find_intent(intents: CaseIntentSet, intent_id: str) -> CaseIntentItem | None:
    for i in intents.intents:
        if i.intent_id == intent_id:
            return i
    return None


def _parse_json_response(raw_response: str) -> dict[str, Any]:
    text = raw_response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise TypeError(f"Expected JSON object, got {type(parsed).__name__}")
    return parsed


def _dump_raw_response(run_dir: Path, raw_response: str, label: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / f"{label}_raw_response.txt").write_text(raw_response, encoding="utf-8")
