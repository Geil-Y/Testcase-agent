"""LLM-A: Requirement Decomposer stage.

Reads requirement input and produces a clarification review with ambiguity
analysis, confidence drivers, and human review scaffolding.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from review_pipeline.artifacts.io import read_json, write_json
from review_pipeline.artifacts.models import (
    RequirementInput,
    RequirementDecomposition,
    ClarificationReview,
    AmbiguityItem,
    FactItem,
    ClarificationQuestion,
    SafeGenerationPolicy,
)
from review_pipeline.artifacts.validation import ValidationResult
from review_pipeline.html_rendering.renderer import render_clarification_review


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
        decomposition = _call_decompose_llm(req, provider)

    review_session_id = f"clarify-{uuid.uuid4().hex[:12]}"
    review = ClarificationReview(
        review_session_id=review_session_id,
        requirement_key=req.requirement_key,
        source_requirement_hash=_hash_text(req.description),
        decomposition=decomposition,
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


def _call_decompose_llm(req: RequirementInput, provider) -> RequirementDecomposition:
    """Call LLM-A for real decomposition. Not yet implemented."""
    raise NotImplementedError("Real LLM provider not wired for decompose stage")


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
