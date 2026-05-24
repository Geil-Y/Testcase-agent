"""Artifact models for the clarification-first review pipeline.

Each artifact is a Pydantic model that defines the JSON contract for a stage
in the pipeline. Code owns plumbing; prompts own generation philosophy.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Requirement Input ──────────────────────────────────────────────────────

class RequirementInput(BaseModel):
    requirement_key: str
    description: str
    function_name: str = ""
    requirement_type: str = "requirement"
    supplementary_info: str = ""


# ── LLM-A: Requirement Decomposition ───────────────────────────────────────

class FactItem(BaseModel):
    item_id: str
    fact_text: str
    source_text: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class AmbiguityItem(BaseModel):
    item_id: str
    affected_text: str
    ambiguity_type: str
    impact: str = ""
    severity: str = "medium"
    clarification_question: str = ""
    safe_generation_policy: str = ""
    recommended_review_decision: str = "mark_needs_review"
    confidence_drivers: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)


class ClarificationQuestion(BaseModel):
    item_id: str
    question: str
    context: str = ""
    relates_to_ambiguity_ids: list[str] = Field(default_factory=list)


class SafeGenerationPolicy(BaseModel):
    can_generate: bool = True
    blocked_dimensions: list[str] = Field(default_factory=list)
    requires_markers: list[str] = Field(default_factory=list)
    notes: str = ""


class RequirementDecomposition(BaseModel):
    """LLM-A output: decomposed requirement with facts, ambiguities, and policy."""

    requirement_key: str
    facts: list[FactItem] = Field(default_factory=list)
    ambiguities: list[AmbiguityItem] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    safe_generation_policy: SafeGenerationPolicy = Field(default_factory=SafeGenerationPolicy)
    confidence_drivers: dict[str, float] = Field(default_factory=dict)


# ── Clarification Review (human-edited) ────────────────────────────────────

class ClarificationDecision(BaseModel):
    item_id: str
    decision: str  # approve, clarify, mark_needs_review, block, edit
    reason_codes: list[str] = Field(default_factory=list)
    reason_text: str = ""
    clarified_value: str = ""
    edited_content: dict[str, Any] = Field(default_factory=dict)
    review_marker_policy: str = ""
    confidence_before_review: float | None = None


class ClarificationReview(BaseModel):
    """Human review decisions on the requirement decomposition."""

    review_session_id: str
    requirement_key: str
    source_requirement_hash: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    decomposition: RequirementDecomposition = Field(default_factory=RequirementDecomposition)
    decisions: list[ClarificationDecision] = Field(default_factory=list)


# ── Clarified Test Basis ───────────────────────────────────────────────────

class ClarifiedTestBasis(BaseModel):
    """Resolved requirement understanding after human clarification review."""

    requirement_key: str
    review_session_id: str
    test_basis_hash: str = ""
    facts: list[FactItem] = Field(default_factory=list)
    resolved_ambiguities: list[dict[str, Any]] = Field(default_factory=list)
    blocked: bool = False
    block_reasons: list[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ── LLM-B: Case Intent Plan ────────────────────────────────────────────────

class CaseIntentItem(BaseModel):
    intent_id: str
    coverage_dimension: str
    intent_text: str
    requirement_basis_refs: list[str] = Field(default_factory=list)
    confidence_drivers: dict[str, float] = Field(default_factory=dict)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    routing_color: str = "blue"
    routing_label: str = ""
    reasons: list[str] = Field(default_factory=list)
    recommended_review_decision: str = "approve"


class CaseIntentPlan(BaseModel):
    """LLM-B output: proposed case intents for review."""

    review_session_id: str
    requirement_key: str
    source_requirement_hash: str = ""
    test_basis_hash: str = ""
    intents: list[CaseIntentItem] = Field(default_factory=list)
    planning_blocked: bool = False
    planning_block_reason: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ── Case Intent Review (human-edited) ──────────────────────────────────────

class CaseIntentDecision(BaseModel):
    intent_id: str
    decision: str  # approve, reject, revise, merge, split, defer
    reason_codes: list[str] = Field(default_factory=list)
    reason_text: str = ""
    revised_intent_text: str = ""
    merge_target_id: str = ""
    split_children: list[CaseIntentItem] = Field(default_factory=list)
    confidence_before_review: float | None = None


class CaseIntentReview(BaseModel):
    """Human review decisions on the case intent plan."""

    review_session_id: str
    requirement_key: str
    source_requirement_hash: str = ""
    test_basis_hash: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    plan: CaseIntentPlan = Field(default_factory=CaseIntentPlan)
    decisions: list[CaseIntentDecision] = Field(default_factory=list)


# ── Approved Case Plan ─────────────────────────────────────────────────────

class ApprovedCasePlan(BaseModel):
    """Final approved case intents, ready for the case writer."""

    review_session_id: str
    requirement_key: str
    source_requirement_hash: str = ""
    test_basis_hash: str = ""
    approved_intents: list[CaseIntentItem] = Field(default_factory=list)
    traceability: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ── LLM-C: Generated Cases ─────────────────────────────────────────────────

class GeneratedCase(BaseModel):
    case_id: str
    title: str = ""
    objective: str = ""
    pre_condition: str = ""
    steps: list[dict[str, str]] = Field(default_factory=list)
    post_condition: str = ""
    requirement_key: str = ""
    approved_intent_id: str = ""
    coverage_dimension: str = ""
    review_session_id: str = ""
    traceability: dict[str, Any] = Field(default_factory=dict)


class GeneratedCaseSet(BaseModel):
    """LLM-C output: generated test cases from approved intents."""

    review_session_id: str
    requirement_key: str
    source_requirement_hash: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    cases: list[GeneratedCase] = Field(default_factory=list)
