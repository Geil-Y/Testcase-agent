"""LLM-A: Requirement Decomposer stage.

Reads requirement input and produces a clarification review with ambiguity
analysis, confidence drivers, and human review scaffolding.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from pydantic import ValidationError

from review_pipeline.artifacts.io import read_json, write_json
from review_pipeline.artifacts.models import (
    RequirementInput,
    RequirementDecomposition,
    ClarificationReview,
    ClarificationDecision,
    AmbiguityItem,
    FactItem,
    ClarificationQuestion,
    SafeGenerationPolicy,
)
from review_pipeline.html_rendering.renderer import render_clarification_review
from review_pipeline.prompts import render_prompt


def prepare_clarification_review(
    input_path: str, out_dir: str, *, provider=None
) -> ClarificationReview:
    """Run the requirement decomposition stage.

    Reads requirements from input_path, calls LLM-A for decomposition,
    and writes clarification_review.json + clarification_review.html.
    """
    requirements = _load_requirements(input_path)
    run_dir = Path(out_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    # For now: single-requirement path
    req = requirements[0]

    if provider is None:
        decomposition = _decompose_placeholder(req)
    else:
        decomposition = _call_decompose_llm(req, provider, run_dir)

    review_session_id = f"clarify-{uuid.uuid4().hex[:12]}"
    decisions = _build_decisions(decomposition)
    review = ClarificationReview(
        review_session_id=review_session_id,
        requirement_key=req.requirement_key,
        source_description=req.description,
        function_name=req.function_name,
        requirement_type=req.requirement_type,
        supplementary_info=req.supplementary_info,
        source_requirement_hash=_hash_text(req.description),
        decomposition=decomposition,
        decisions=decisions,
    )

    json_path = run_dir / "clarification_review.json"
    write_json(json_path, review.model_dump())

    html_path = run_dir / "clarification_review.html"
    html_path.write_text(render_clarification_review(review), encoding="utf-8")

    return review


def _load_requirements(path: str) -> list[RequirementInput]:
    data = read_json(path)
    if isinstance(data, list):
        return [RequirementInput(**item) for item in data]
    if isinstance(data, dict):
        if "requirements" in data:
            return [RequirementInput(**item) for item in data["requirements"]]
        return [RequirementInput(**data)]
    raise ValueError(f"Unsupported input format: {type(data)}")


def _call_decompose_llm(
    req: RequirementInput,
    provider,
    run_dir: Path,
) -> RequirementDecomposition:
    """Call LLM-A and parse its JSON response into a decomposition artifact."""
    system_prompt, user_prompt = render_prompt(
        "decompose_requirement",
        requirement_key=req.requirement_key,
        description=req.description,
        function_name=req.function_name,
        requirement_type=req.requirement_type,
        supplementary_info=req.supplementary_info,
    )
    raw_response = provider.complete(system_prompt, user_prompt)

    try:
        payload = _parse_json_response(raw_response)
        return RequirementDecomposition(**payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        _dump_raw_response(run_dir, raw_response)
        raise ValueError(f"LLM-A response was not valid JSON decomposition: {exc}") from exc


def _parse_json_response(raw_response: str) -> dict:
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


def _decompose_placeholder(req: RequirementInput) -> RequirementDecomposition:
    """Placeholder decomposition for testing without a real LLM."""
    return RequirementDecomposition(
        requirement_key=req.requirement_key,
        facts=[
            FactItem(item_id="fact-1", fact_text=req.description, source_text=req.description, confidence=0.9),
        ],
        ambiguities=[
            AmbiguityItem(
                item_id="amb-1",
                affected_text=req.description[:100],
                ambiguity_type="timing",
                impact="Cannot determine response timing for verification",
                severity="medium",
                clarification_question="What is the expected response time?",
                safe_generation_policy="mark_with_needs_review",
                confidence_drivers={
                    "trigger_clarity": 0.8,
                    "expected_behavior_clarity": 0.7,
                    "known_info_sufficiency": 0.5,
                    "ambiguity_resolution": 0.3,
                    "historical_pattern_support": 0.5,
                },
                reasons=["Timing not specified in requirement"],
            ),
        ],
        clarification_questions=[
            ClarificationQuestion(
                item_id="q-1",
                question="What is the expected response time?",
                context="Requirement describes behavior but not latency",
                relates_to_ambiguity_ids=["amb-1"],
            ),
        ],
        safe_generation_policy=SafeGenerationPolicy(
            can_generate=True,
            requires_markers=["timing"],
            notes="Generation allowed with NEEDS REVIEW markers for timing",
        ),
        confidence_drivers={
            "trigger_clarity": 0.8,
            "expected_behavior_clarity": 0.7,
            "known_info_sufficiency": 0.5,
            "ambiguity_resolution": 0.3,
            "historical_pattern_support": 0.5,
        },
    )


def _hash_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _build_decisions(decomposition: RequirementDecomposition) -> list[ClarificationDecision]:
    """Pre-populate review decisions from LLM-A recommendations."""
    decisions = []
    for amb in decomposition.ambiguities:
        score = None
        if amb.confidence_drivers:
            score = sum(amb.confidence_drivers.values()) / len(amb.confidence_drivers)
        decisions.append(ClarificationDecision(
            item_id=amb.item_id,
            decision=amb.recommended_review_decision,
            confidence_before_review=score,
        ))
    return decisions
