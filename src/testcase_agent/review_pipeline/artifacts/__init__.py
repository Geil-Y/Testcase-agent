"""Re-export new and legacy models for backward compatibility.

New pipeline: ExtractedTestBasis, CaseIntentSet, GeneratedCaseSet, etc.
Legacy pipeline: RequirementDecomposition, ClarificationReview, etc. (re-exported from legacy_models)
"""

from testcase_agent.review_pipeline.artifacts.models import (
    RequirementInput,
    ExtractedTestBasis,
    SectionItem,
    CaseIntentItem,
    CaseIntentSet,
    GeneratedCase,
    GeneratedCaseSet,
    ExtractionReviewAction,
    IntentReviewAction,
    RegenerateRequest,
)
from testcase_agent.review_pipeline.artifacts.legacy_models import (
    RequirementDecomposition,
    FactItem,
    AmbiguityItem,
    ClarificationQuestion,
    SafeGenerationPolicy,
    ClarificationReview,
    ClarificationDecision,
    ClarifiedTestBasis,
    CaseIntentPlan,
    LegacyCaseIntentItem,
    CaseIntentDecision,
    CaseIntentReview,
    ApprovedCasePlan,
    LegacyGeneratedCaseSet,
)
from testcase_agent.review_pipeline.artifacts.io import read_json, write_json
from testcase_agent.review_pipeline.artifacts.validation import ValidationError, ValidationResult

__all__ = [
    "RequirementInput",
    "ExtractedTestBasis",
    "SectionItem",
    "CaseIntentItem",
    "CaseIntentSet",
    "GeneratedCase",
    "GeneratedCaseSet",
    "ExtractionReviewAction",
    "IntentReviewAction",
    "RegenerateRequest",
    "RequirementDecomposition",
    "FactItem",
    "AmbiguityItem",
    "ClarificationQuestion",
    "SafeGenerationPolicy",
    "ClarificationReview",
    "ClarificationDecision",
    "ClarifiedTestBasis",
    "CaseIntentPlan",
    "LegacyCaseIntentItem",
    "CaseIntentDecision",
    "CaseIntentReview",
    "ApprovedCasePlan",
    "LegacyGeneratedCaseSet",
    "read_json",
    "write_json",
    "ValidationError",
    "ValidationResult",
]
