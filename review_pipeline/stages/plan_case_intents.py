"""LLM-B: Case Intent Planner stage.

Reads the original requirement, decomposition, clarified test basis,
and optional Review Memory hints. Produces case_intent_review.json + HTML.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from review_pipeline.artifacts.io import read_json, write_json
from review_pipeline.artifacts.models import (
    RequirementInput,
    RequirementDecomposition,
    ClarifiedTestBasis,
    CaseIntentPlan,
    CaseIntentReview,
    CaseIntentItem,
    ClarificationReview,
)
from review_pipeline.artifacts.validation import ValidationResult
from review_pipeline.html_rendering.renderer import render_case_intent_review


def prepare_intent_review(run_dir: str, *, provider=None, memory_hints: dict | None = None) -> CaseIntentReview:
    """Run the case intent planning stage.

    Reads clarified_test_basis.json and (optionally) clarification_review.json
    from run_dir. Produces case_intent_review.json + case_intent_review.html.
    """
    rdir = Path(run_dir)

    # Load required inputs
    basis = ClarifiedTestBasis(**read_json(rdir / "clarified_test_basis.json"))

    # Load original review for context
    review_path = rdir / "clarification_review.json"
    review = ClarificationReview(**read_json(review_path)) if review_path.exists() else None

    if basis.blocked:
        plan = CaseIntentPlan(
            review_session_id=basis.review_session_id,
            requirement_key=basis.requirement_key,
            source_requirement_hash=review.source_requirement_hash if review else "",
            test_basis_hash=basis.test_basis_hash,
            planning_blocked=True,
            planning_block_reason="; ".join(basis.block_reasons),
        )
    elif provider is None:
        plan = _plan_placeholder(basis, review, memory_hints)
    else:
        plan = _call_plan_llm(basis, review, provider, memory_hints)

    intent_review = CaseIntentReview(
        review_session_id=f"intent-{uuid.uuid4().hex[:12]}",
        requirement_key=basis.requirement_key,
        source_requirement_hash=review.source_requirement_hash if review else "",
        test_basis_hash=basis.test_basis_hash,
        plan=plan,
    )

    write_json(rdir / "case_intent_review.json", intent_review.model_dump())
    html_path = rdir / "case_intent_review.html"
    html_path.write_text(render_case_intent_review(intent_review), encoding="utf-8")

    return intent_review


def _call_plan_llm(basis: ClarifiedTestBasis, review: ClarificationReview | None, provider, memory_hints: dict | None) -> CaseIntentPlan:
    """Call LLM-B for real intent planning. Not yet implemented."""
    raise NotImplementedError("Real LLM provider not wired for plan stage")


def _plan_placeholder(basis: ClarifiedTestBasis, review: ClarificationReview | None, memory_hints: dict | None = None) -> CaseIntentPlan:
    """Placeholder intent planning for testing without a real LLM."""
    return CaseIntentPlan(
        review_session_id=basis.review_session_id,
        requirement_key=basis.requirement_key,
        source_requirement_hash=review.source_requirement_hash if review else "",
        test_basis_hash=basis.test_basis_hash,
        intents=[
            CaseIntentItem(
                intent_id="intent-1",
                coverage_dimension="normal_behavior",
                intent_text=f"Verify normal operation of {basis.requirement_key}",
                requirement_basis_refs=["fact-1"],
                confidence_drivers={
                    "requirement_basis_strength": 0.8,
                    "separate_case_value": 0.7,
                    "missing_info_handling": 0.6,
                    "historical_decision_support": 0.5,
                },
                confidence_score=0.65,
                routing_color="blue",
                routing_label="Review recommended",
                reasons=["Standard verification case"],
                recommended_review_decision="approve",
            ),
            CaseIntentItem(
                intent_id="intent-2",
                coverage_dimension="boundary_or_threshold",
                intent_text=f"Verify threshold behavior of {basis.requirement_key}",
                requirement_basis_refs=["fact-1"],
                confidence_drivers={
                    "requirement_basis_strength": 0.6,
                    "separate_case_value": 0.7,
                    "missing_info_handling": 0.4,
                    "historical_decision_support": 0.5,
                },
                confidence_score=0.55,
                routing_color="orange",
                routing_label="Review required",
                reasons=["Threshold values not explicitly specified"],
                recommended_review_decision="revise",
            ),
        ],
    )
