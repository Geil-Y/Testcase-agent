"""Artifact models for the simplified A/B/C reviewed pipeline.

ADP-0005 pipeline split:
  LLM-A extraction -> review -> LLM-B planning -> review -> LLM-C writing -> review

Each LLM output artifact and its ``reviewed_*`` counterpart use the same schema.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ═══════════════════════════════════════════════════════════════════════════════
# Requirement Input
# ═══════════════════════════════════════════════════════════════════════════════

class RequirementInput(BaseModel):
    requirement_key: str
    description: str
    function_name: str = ""
    requirement_type: str = "requirement"
    supplementary_info: str = ""


# ═══════════════════════════════════════════════════════════════════════════════
# LLM-A: Extracted Test Basis (and reviewed counterpart, same schema)
# ═══════════════════════════════════════════════════════════════════════════════

ALLOWED_SECTION_NAMES = frozenset({
    "signals", "thresholds", "timing", "states", "observations",
})


class SectionItem(BaseModel):
    """One item inside an extracted test basis section.

    - status="known": ``content`` must have a value backed by the requirement.
    - status="needs_review": ``need`` must describe what information is missing.
    """
    item_id: str
    status: Literal["known", "needs_review"] = "known"
    content: str = ""
    need: str = ""
    source_text: str = ""

    @model_validator(mode="after")
    def _enforce_status_semantics(self) -> "SectionItem":
        if self.status == "known" and not self.content.strip():
            raise ValueError(
                f"SectionItem {self.item_id!r}: status='known' requires non-empty 'content'")
        if self.status == "needs_review" and not self.need.strip():
            raise ValueError(
                f"SectionItem {self.item_id!r}: status='needs_review' requires non-empty 'need'")
        return self


class ExtractedTestBasis(BaseModel):
    """LLM-A output: five evidence sections extracted from the requirement description.

    Also used as the schema for ``reviewed_extracted_test_basis.json``.
    """

    requirement_key: str
    source_description: str = ""
    sections: dict[str, list[SectionItem]] = Field(default_factory=lambda: {
        name: [] for name in ALLOWED_SECTION_NAMES
    })
    blocking_gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _enforce_section_names(self) -> "ExtractedTestBasis":
        extra = set(self.sections.keys()) - ALLOWED_SECTION_NAMES
        if extra:
            raise ValueError(
                f"ExtractedTestBasis sections must be one of {sorted(ALLOWED_SECTION_NAMES)}. "
                f"Got extra keys: {sorted(extra)}")
        return self

    @property
    def has_blocking_gaps(self) -> bool:
        return len(self.blocking_gaps) > 0

    def known_items(self, section: str) -> list[SectionItem]:
        return [i for i in self.sections.get(section, []) if i.status == "known"]

    def needs_review_items(self, section: str) -> list[SectionItem]:
        return [i for i in self.sections.get(section, []) if i.status == "needs_review"]

    def all_needs_review_items(self) -> list[SectionItem]:
        result: list[SectionItem] = []
        for sec in ALLOWED_SECTION_NAMES:
            result.extend(self.needs_review_items(sec))
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# LLM-B: Case Intents (and reviewed counterpart, same schema)
# ═══════════════════════════════════════════════════════════════════════════════

VALID_COVERAGE_DIMENSIONS = frozenset({
    "normal_behavior", "boundary_or_threshold", "fault_or_protection",
    "state_transition", "observability",
})


class CaseIntentItem(BaseModel):
    """One planned case intent — coverage dimension + one-sentence intent text.

    No confidence routing, reasons, or item-level basis references.
    """
    intent_id: str
    coverage_dimension: str = ""
    intent_text: str = ""

    @model_validator(mode="after")
    def _enforce_fields(self) -> "CaseIntentItem":
        if not self.intent_text.strip():
            raise ValueError(
                f"CaseIntentItem {self.intent_id!r}: 'intent_text' must be non-empty")
        return self


class CaseIntentSet(BaseModel):
    """LLM-B output: coverage plan from reviewed extraction.

    Also used as the schema for ``reviewed_case_intents.json``.
    """

    requirement_key: str
    source_description: str = ""
    intents: list[CaseIntentItem] = Field(default_factory=list)
    blocking_gaps: list[str] = Field(default_factory=list)

    @property
    def has_blocking_gaps(self) -> bool:
        return len(self.blocking_gaps) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# LLM-C: Generated Cases (and reviewed counterpart, same schema)
# ═══════════════════════════════════════════════════════════════════════════════

class GeneratedCase(BaseModel):
    case_id: str
    title: str = ""
    objective: str = ""
    pre_condition: str = ""
    steps: list[dict[str, str]] = Field(default_factory=list)
    post_condition: str = ""
    requirement_key: str = ""
    intent_id: str = ""
    coverage_dimension: str = ""


class GeneratedCaseSet(BaseModel):
    """LLM-C output: generated test cases.

    Also used as the schema for ``reviewed_cases.json``.
    BOTH ``generated_cases.json`` and ``reviewed_cases.json`` use this same object shape.
    """

    requirement_key: str
    source_description: str = ""
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    cases: list[GeneratedCase] = Field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Review action helpers
# ═══════════════════════════════════════════════════════════════════════════════

EXTRACTION_REVIEW_ACTIONS = frozenset({"accept", "edit", "add", "remove", "block"})
INTENT_REVIEW_ACTIONS = frozenset({"accept", "edit", "add", "remove", "block"})


class ExtractionReviewAction(BaseModel):
    """A single review action on an extraction item."""
    item_id: str
    section: str
    action: str
    edited_item: SectionItem | None = None
    new_item: SectionItem | None = None

    @model_validator(mode="after")
    def _enforce_action_semantics(self) -> "ExtractionReviewAction":
        if self.action not in EXTRACTION_REVIEW_ACTIONS:
            raise ValueError(
                f"ExtractionReviewAction: unknown action {self.action!r}. "
                f"Must be one of: {sorted(EXTRACTION_REVIEW_ACTIONS)}")
        if self.action == "edit" and self.edited_item is None:
            raise ValueError("action='edit' requires edited_item")
        if self.action == "add" and self.new_item is None:
            raise ValueError("action='add' requires new_item")
        return self


class IntentReviewAction(BaseModel):
    """A single review action on a case intent."""
    intent_id: str
    action: str
    edited_intent: CaseIntentItem | None = None
    new_intent: CaseIntentItem | None = None

    @model_validator(mode="after")
    def _enforce_action_semantics(self) -> "IntentReviewAction":
        if self.action not in INTENT_REVIEW_ACTIONS:
            raise ValueError(
                f"IntentReviewAction: unknown action {self.action!r}. "
                f"Must be one of: {sorted(INTENT_REVIEW_ACTIONS)}")
        if self.action == "edit" and self.edited_intent is None:
            raise ValueError("action='edit' requires edited_intent")
        if self.action == "add" and self.new_intent is None:
            raise ValueError("action='add' requires new_intent")
        return self


class RegenerateRequest(BaseModel):
    """Request to regenerate a case with a review comment."""
    case_id: str
    intent_id: str
    review_comment: str

    @model_validator(mode="after")
    def _enforce_comment_nonempty(self) -> "RegenerateRequest":
        if not self.review_comment.strip():
            raise ValueError("RegenerateRequest: review_comment must be non-empty")
        return self


# ═══════════════════════════════════════════════════════════════════════════════
# Re-export legacy models for backward compatibility with tests and legacy code.
# New pipeline code must NOT use these.
# ═══════════════════════════════════════════════════════════════════════════════

from testcase_agent.review_pipeline.artifacts.legacy_models import (
    FactItem,
    AmbiguityItem,
    ClarificationQuestion,
    SafeGenerationPolicy,
    RequirementDecomposition,
    ClarificationDecision,
    ClarificationReview,
    ClarifiedTestBasis,
    LegacyCaseIntentItem,
    CaseIntentPlan,
    CaseIntentDecision,
    CaseIntentReview,
    ApprovedCasePlan,
    LegacyGeneratedCaseSet,
)

