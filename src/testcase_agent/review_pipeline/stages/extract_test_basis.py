"""LLM-A: Test Basis Extraction stage.

Reads a requirement description and extracts five evidence sections:
signals, thresholds, timing, states, and observations.

Writes ``extracted_test_basis.json``. Accept All or human review writes
``reviewed_extracted_test_basis.json`` using the same schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from testcase_agent.review_pipeline.artifacts.io import read_json, write_json
from testcase_agent.review_pipeline.artifacts.models import (
    RequirementInput,
    ExtractedTestBasis,
    SectionItem,
    ExtractionReviewAction,
)
from testcase_agent.review_pipeline.artifacts.validation import validate_accept_all_no_blocking_gaps
from testcase_agent.review_pipeline.prompts import render_prompt


# ── Stage: Extract test basis ──────────────────────────────────────────────────

def extract_test_basis(
    input_path: str, out_dir: str, *, provider=None
) -> ExtractedTestBasis:
    """Run LLM-A extraction.

    Reads requirement from input_path, calls LLM-A, and writes
    ``extracted_test_basis.json`` to out_dir.
    """
    requirements = _load_requirements(input_path)
    run_dir = Path(out_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    req = requirements[0]

    if provider is None:
        basis = _extract_placeholder(req)
    else:
        basis = _call_extract_llm(req, provider, run_dir)

    json_path = run_dir / "extracted_test_basis.json"
    write_json(json_path, basis.model_dump())

    return basis


# ── Review: Accept All ─────────────────────────────────────────────────────────

def accept_extraction(run_dir: str | Path) -> ExtractedTestBasis:
    """Accept All: copy extracted_test_basis.json to reviewed_extracted_test_basis.json.

    Raises ValueError if blocking_gaps are present (must be resolved first).
    """
    rdir = Path(run_dir)
    src = rdir / "extracted_test_basis.json"
    dst = rdir / "reviewed_extracted_test_basis.json"

    if not src.exists():
        raise ValueError("extracted_test_basis.json not found — run extraction first.")

    validation = validate_accept_all_no_blocking_gaps(src, artifact_label="extracted_test_basis.json")
    if not validation.is_valid:
        raise ValueError(f"Cannot Accept All: {validation.format_errors()}")

    data = read_json(src)
    write_json(dst, data)
    return ExtractedTestBasis(**data)


# ── Review: Apply review actions ───────────────────────────────────────────────

def apply_extraction_review(
    run_dir: str | Path,
    actions: list[ExtractionReviewAction],
) -> ExtractedTestBasis:
    """Apply human review actions to extracted_test_basis and write reviewed version.

    Actions are applied to a copy of the extracted artifact. The result is
    written as ``reviewed_extracted_test_basis.json``.
    """
    rdir = Path(run_dir)
    src = rdir / "extracted_test_basis.json"
    if not src.exists():
        raise ValueError("extracted_test_basis.json not found — run extraction first.")

    basis = ExtractedTestBasis(**read_json(src))

    for action in actions:
        section = action.section
        if section not in basis.sections:
            basis.sections[section] = []

        if action.action == "accept":
            _action_accept(basis, action)
        elif action.action == "edit":
            _action_edit(basis, action)
        elif action.action == "add":
            _action_add(basis, action)
        elif action.action == "remove":
            _action_remove(basis, action)
        elif action.action == "block":
            _action_block(basis, action)

    write_json(rdir / "reviewed_extracted_test_basis.json", basis.model_dump())
    return basis


def _action_accept(basis: ExtractedTestBasis, action: ExtractionReviewAction) -> None:
    """Accept keeps the item as-is."""
    pass  # item is already in the basis


def _action_edit(basis: ExtractedTestBasis, action: ExtractionReviewAction) -> None:
    """Replace an existing item with the edited version."""
    _action_remove(basis, action)
    if action.edited_item is not None:
        basis.sections[action.section].append(action.edited_item)


def _action_add(basis: ExtractedTestBasis, action: ExtractionReviewAction) -> None:
    """Add a new item to the section."""
    if action.new_item is not None:
        basis.sections[action.section].append(action.new_item)


def _action_remove(basis: ExtractedTestBasis, action: ExtractionReviewAction) -> None:
    """Remove an item from the section."""
    items = basis.sections[action.section]
    basis.sections[action.section] = [i for i in items if i.item_id != action.item_id]


def _action_block(basis: ExtractedTestBasis, action: ExtractionReviewAction) -> None:
    """Add a blocking gap reason."""
    if action.new_item is not None and action.new_item.need:
        basis.blocking_gaps.append(action.new_item.need)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _load_requirements(path: str) -> list[RequirementInput]:
    data = read_json(path)
    if isinstance(data, list):
        return [RequirementInput(**item) for item in data]
    if isinstance(data, dict):
        if "requirements" in data:
            return [RequirementInput(**item) for item in data["requirements"]]
        return [RequirementInput(**data)]
    raise ValueError(f"Unsupported input format: {type(data)}")


def _call_extract_llm(
    req: RequirementInput, provider, run_dir: Path
) -> ExtractedTestBasis:
    """Call LLM-A and parse its JSON response into an ExtractedTestBasis."""
    system_prompt, user_prompt = render_prompt(
        "extract_test_basis",
        requirement_key=req.requirement_key,
        description=req.description,
        function_name=req.function_name,
        requirement_type=req.requirement_type,
        # supplementary_info intentionally NOT passed
    )
    raw_response = provider.complete(system_prompt, user_prompt)

    try:
        payload = _parse_json_response(raw_response)
        return ExtractedTestBasis(**payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        _dump_raw_response(run_dir, raw_response)
        raise ValueError(f"LLM-A response was not valid JSON: {exc}") from exc


def _extract_placeholder(req: RequirementInput) -> ExtractedTestBasis:
    """Placeholder extraction for testing without a real LLM."""
    return ExtractedTestBasis(
        requirement_key=req.requirement_key,
        source_description=req.description,
        sections={
            "signals": [],
            "thresholds": [
                SectionItem(
                    item_id="thr-1",
                    status="needs_review",
                    content="",
                    need="Threshold value for the trigger condition",
                    source_text=req.description[:100],
                ),
            ],
            "timing": [
                SectionItem(
                    item_id="tim-1",
                    status="needs_review",
                    content="",
                    need="Timing parameter for debounce or response delay",
                    source_text=req.description[:100],
                ),
            ],
            "states": [],
            "observations": [],
        },
        blocking_gaps=[],
    )


def _parse_json_response(raw_response: str) -> dict[str, Any]:
    """Parse raw model output that should contain exactly one JSON object."""
    text = raw_response.strip()
    if text.startswith("```"):
        text = _strip_markdown_fence(text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise TypeError(f"Expected JSON object, got {type(parsed).__name__}")
    return parsed


def _strip_markdown_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _dump_raw_response(run_dir: Path, raw_response: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "llm_a_raw_response.txt").write_text(raw_response, encoding="utf-8")
