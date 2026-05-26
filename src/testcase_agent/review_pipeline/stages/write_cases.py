"""LLM-C: Case Writer stage.

Reads approved_case_plan.json and generates one test case per approved intent.
Does NOT call self_check. Preserves traceability.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from testcase_agent.review_pipeline.artifacts.io import read_json, write_json
from testcase_agent.review_pipeline.artifacts.models import (
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
    """Call LLM-C for real case writing."""
    import json
    from pydantic import ValidationError
    from testcase_agent.review_pipeline.prompts import render_prompt

    facts_summary = ""
    description = plan.requirement_key
    supplementary_info = ""
    missing_info = ""
    if basis:
        description = basis.source_description or plan.requirement_key
        supplementary_info = basis.supplementary_info
        facts_summary = "\n".join(f"- [{f.item_id}] {f.fact_text}" for f in basis.facts)
        missing_info = _format_missing_info_for_prompt(basis)

    system_prompt, user_prompt = render_prompt(
        "write_case",
        requirement_key=plan.requirement_key,
        description=description,
        facts_summary=facts_summary,
        intent_id=intent.intent_id,
        coverage_dimension=intent.coverage_dimension,
        intent_text=intent.intent_text,
        supplementary_info=supplementary_info,
        missing_info=missing_info,
    )
    raw_response = provider.complete(system_prompt, user_prompt)

    try:
        payload = _parse_json_response(raw_response)
        payload.setdefault("case_id", f"case-{uuid.uuid4().hex[:8]}")
        payload.setdefault("requirement_key", plan.requirement_key)
        payload.setdefault("approved_intent_id", intent.intent_id)
        payload.setdefault("coverage_dimension", intent.coverage_dimension)
        payload.setdefault("review_session_id", plan.review_session_id)
        # Coerce step_number to string (LLM may emit int)
        for step in payload.get("steps", []):
            if "step_number" in step:
                step["step_number"] = str(step["step_number"])
        return GeneratedCase(**payload)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise ValueError(f"LLM-C response was not valid JSON: {exc}") from exc


def _format_missing_info_for_prompt(basis: ClarifiedTestBasis) -> str:
    """Summarize unresolved semantic gaps that require NEEDS REVIEW markers."""
    lines: list[str] = []
    for item in basis.resolved_ambiguities:
        decision = item.get("decision", "")
        clarified_value = item.get("clarified_value", "")
        if decision == "mark_needs_review" or (decision in {"clarify", "edit"} and not clarified_value):
            ambiguity_type = item.get("ambiguity_type") or "unspecified"
            affected_text = item.get("affected_text") or item.get("item_id", "")
            lines.append(f"- {ambiguity_type}: {affected_text}")
    return "\n".join(lines)


def _parse_json_response(raw_response: str) -> dict:
    text = raw_response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    import json
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise TypeError(f"Expected JSON object, got {type(parsed).__name__}")
    return parsed


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
