"""LLM-C: Case Writer stage.

Reads approved_case_plan.json and generates one test case per approved intent.
Does NOT call self_check. Preserves traceability.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from review_pipeline.artifacts.io import read_json, write_json
from review_pipeline.artifacts.models import (
    ApprovedCasePlan,
    CaseIntentItem,
    GeneratedCase,
    GeneratedCaseSet,
    ClarifiedTestBasis,
)


def generate_cases(run_dir: str, *, provider=None) -> GeneratedCaseSet:
    """Generate test cases from the approved case plan.

    Generates exactly one case per approved intent.
    Skips rejected, merged-away, split-parent, and deferred intents.
    """
    rdir = Path(run_dir)

    plan = ApprovedCasePlan(**read_json(rdir / "approved_case_plan.json"))

    basis = None
    basis_path = rdir / "clarified_test_basis.json"
    if basis_path.exists():
        basis = ClarifiedTestBasis(**read_json(basis_path))

    cases: list[GeneratedCase] = []
    for intent in plan.approved_intents:
        if provider is None:
            case = _write_case_placeholder(plan, intent, basis)
        else:
            case = _call_write_case_llm(plan, intent, basis, provider)
        cases.append(case)

    case_set = GeneratedCaseSet(
        review_session_id=plan.review_session_id,
        requirement_key=plan.requirement_key,
        source_requirement_hash=plan.source_requirement_hash,
        cases=cases,
    )

    write_json(rdir / "generated_cases.json", [c.model_dump() for c in cases])

    return case_set


def _call_write_case_llm(plan: ApprovedCasePlan, intent: CaseIntentItem, basis: ClarifiedTestBasis | None, provider) -> GeneratedCase:
    """Call LLM-C for real case writing. Not yet implemented."""
    raise NotImplementedError("Real LLM provider not wired for write stage")


def _write_case_placeholder(plan: ApprovedCasePlan, intent: CaseIntentItem, basis: ClarifiedTestBasis | None) -> GeneratedCase:
    """Placeholder case generation for testing without a real LLM."""
    case_id = f"case-{uuid.uuid4().hex[:8]}"
    return GeneratedCase(
        case_id=case_id,
        title=intent.intent_text,
        objective=f"Verify {intent.coverage_dimension} behavior",
        pre_condition="System is in normal operating state",
        steps=[
            {"action": "Set up test conditions per requirement", "expected_result": "System responds correctly"},
            {"action": "Execute verification step", "expected_result": "Behavior matches specification"},
        ],
        post_condition="System returns to normal state",
        requirement_key=plan.requirement_key,
        approved_intent_id=intent.intent_id,
        coverage_dimension=intent.coverage_dimension,
        review_session_id=plan.review_session_id,
        traceability={
            "requirement_key": plan.requirement_key,
            "approved_intent_id": intent.intent_id,
            "coverage_dimension": intent.coverage_dimension,
            "review_session_id": plan.review_session_id,
        },
    )
