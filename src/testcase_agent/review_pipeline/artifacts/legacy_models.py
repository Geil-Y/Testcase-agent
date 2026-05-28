"""Legacy artifact models — preserved for backward compatibility with tests.

NOT used by the simplified A/B/C pipeline. These models support the old
facts/ambiguities/confidence routing/clarification review data model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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
    requirement_key: str
    facts: list[FactItem] = Field(default_factory=list)
    ambiguities: list[AmbiguityItem] = Field(default_factory=list)
    clarification_questions: list[ClarificationQuestion] = Field(default_factory=list)
    safe_generation_policy: SafeGenerationPolicy = Field(default_factory=SafeGenerationPolicy)
    confidence_drivers: dict[str, float] = Field(default_factory=dict)


class ClarificationDecision(BaseModel):
    item_id: str
    decision: str
    reason_codes: list[str] = Field(default_factory=list)
    reason_text: str = ""
    clarified_value: str = ""
    edited_content: dict[str, Any] = Field(default_factory=dict)
    review_marker_policy: str = ""
    confidence_before_review: float | None = None


class ClarificationReview(BaseModel):
    review_session_id: str
    requirement_key: str
    source_description: str = ""
    function_name: str = ""
    requirement_type: str = ""
    supplementary_info: str = ""
    source_requirement_hash: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    decomposition: RequirementDecomposition = Field(default_factory=RequirementDecomposition)
    decisions: list[ClarificationDecision] = Field(default_factory=list)


class ClarifiedTestBasis(BaseModel):
    requirement_key: str
    review_session_id: str
    source_description: str = ""
    function_name: str = ""
    requirement_type: str = ""
    supplementary_info: str = ""
    test_basis_hash: str = ""
    facts: list[FactItem] = Field(default_factory=list)
    resolved_ambiguities: list[dict[str, Any]] = Field(default_factory=list)
    blocked: bool = False
    block_reasons: list[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class LegacyCaseIntentItem(BaseModel):
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
    review_session_id: str
    requirement_key: str
    source_requirement_hash: str = ""
    test_basis_hash: str = ""
    intents: list[LegacyCaseIntentItem] = Field(default_factory=list)
    planning_blocked: bool = False
    planning_block_reason: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class CaseIntentDecision(BaseModel):
    intent_id: str
    decision: str
    reason_codes: list[str] = Field(default_factory=list)
    reason_text: str = ""
    revised_intent_text: str = ""
    merge_target_id: str = ""
    split_children: list[LegacyCaseIntentItem] = Field(default_factory=list)
    confidence_before_review: float | None = None


class CaseIntentReview(BaseModel):
    review_session_id: str
    requirement_key: str
    source_requirement_hash: str = ""
    test_basis_hash: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    plan: CaseIntentPlan = Field(default_factory=CaseIntentPlan)
    decisions: list[CaseIntentDecision] = Field(default_factory=list)


class ApprovedCasePlan(BaseModel):
    review_session_id: str
    requirement_key: str
    source_requirement_hash: str = ""
    test_basis_hash: str = ""
    approved_intents: list[LegacyCaseIntentItem] = Field(default_factory=list)
    traceability: list[dict[str, Any]] = Field(default_factory=list)
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# Re-export GeneratedCase / GeneratedCaseSet from main models for convenience
from testcase_agent.review_pipeline.artifacts.models import GeneratedCase


class LegacyGeneratedCaseSet(BaseModel):
    review_session_id: str
    requirement_key: str
    source_requirement_hash: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    cases: list[GeneratedCase] = Field(default_factory=list)
