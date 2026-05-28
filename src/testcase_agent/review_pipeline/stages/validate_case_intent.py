"""Issue 9: Case intent review validation and approved case plan.

Validates human-edited case_intent_review.json and produces
approved_case_plan.json for the case writer.
"""

from __future__ import annotations

from pathlib import Path

from testcase_agent.review_pipeline.artifacts.io import read_json, write_json
from testcase_agent.review_pipeline.artifacts.legacy_models import (
    CaseIntentReview,
    CaseIntentDecision,
    LegacyCaseIntentItem as CaseIntentItem,
    ApprovedCasePlan,
)
from testcase_agent.review_pipeline.artifacts.validation import ValidationResult
from testcase_agent.review_pipeline.reason_codes import (
    is_decision_valid,
    is_reason_code_valid,
    get_decision_requirements,
    requires_reason_text_on_conflict,
)


def validate_case_intent_review(file_path: str) -> tuple[ValidationResult, ApprovedCasePlan | None]:
    """Validate a human-edited case intent review JSON and produce approved case plan."""
    result = ValidationResult()
    data = read_json(file_path)
    review = CaseIntentReview(**data)

    approved_intents: list[CaseIntentItem] = []
    traceability: list[dict] = []

    # Build lookup for original intents
    intent_map: dict[str, CaseIntentItem] = {}
    for intent in review.plan.intents:
        intent_map[intent.intent_id] = intent

    for dec in review.decisions:
        _validate_intent_decision(dec, intent_map, review, result)
        if result.errors:
            continue

        traceability.append({
            "intent_id": dec.intent_id,
            "decision": dec.decision,
            "reason_codes": dec.reason_codes,
            "reason_text": dec.reason_text,
        })

        if dec.decision == "approve":
            original = intent_map.get(dec.intent_id)
            if original and dec.revised_intent_text:
                approved_intents.append(original.model_copy(update={"intent_text": dec.revised_intent_text}))
            elif original:
                approved_intents.append(original)

        elif dec.decision == "revise":
            original = intent_map.get(dec.intent_id)
            if original:
                approved_intents.append(original.model_copy(update={
                    "intent_text": dec.revised_intent_text or original.intent_text,
                }))

        elif dec.decision == "split":
            for child in dec.split_children:
                approved_intents.append(child)

        elif dec.decision == "merge":
            target = intent_map.get(dec.merge_target_id)
            if target and target not in approved_intents:
                approved_intents.append(target)
            # Merged-away intent is NOT added

        # reject and defer: intent is NOT added to approved plan

    if result.errors:
        return result, None

    plan = ApprovedCasePlan(
        review_session_id=review.review_session_id,
        requirement_key=review.requirement_key,
        source_requirement_hash=review.source_requirement_hash,
        test_basis_hash=review.test_basis_hash,
        approved_intents=approved_intents,
        traceability=traceability,
    )

    run_dir = Path(file_path).parent
    write_json(run_dir / "approved_case_plan.json", plan.model_dump())

    return result, plan


def _validate_intent_decision(
    dec: CaseIntentDecision,
    intent_map: dict[str, CaseIntentItem],
    review: CaseIntentReview,
    result: ValidationResult,
) -> None:
    artifact_path = f"case_intent_review.json / decisions / {dec.intent_id}"

    if not is_decision_valid("case_intent_item", dec.decision):
        result.add_error(artifact_path, "decision", f"Unknown decision: {dec.decision}")
        return

    reqs = get_decision_requirements(dec.decision)

    # Reason code requirements
    if reqs.get("require_reason_code") and not dec.reason_codes:
        result.add_error(artifact_path, "reason_codes",
                         f"Decision '{dec.decision}' requires at least one reason code")
    else:
        for rc in dec.reason_codes:
            if not is_reason_code_valid("case_intent_item", rc):
                result.add_error(artifact_path, "reason_codes", f"Unknown reason code: {rc}")

    # Reason text requirements
    if reqs.get("require_reason_text") and not dec.reason_text:
        result.add_error(artifact_path, "reason_text",
                         f"Decision '{dec.decision}' requires reason text")

    # Decision-specific validation
    if dec.decision == "merge":
        if not dec.merge_target_id:
            result.add_error(artifact_path, "merge_target_id", "Merge requires target intent id")
        elif dec.merge_target_id not in intent_map:
            result.add_error(artifact_path, "merge_target_id", f"Unknown merge target: {dec.merge_target_id}")
        elif dec.merge_target_id == dec.intent_id:
            result.add_error(artifact_path, "merge_target_id", "Cannot merge into itself")

    if dec.decision == "split":
        if not dec.split_children:
            result.add_error(artifact_path, "split_children", "Split requires at least one child intent")

    # Confidence/decision conflict check
    if dec.confidence_before_review is not None and requires_reason_text_on_conflict():
        agent_conf = dec.confidence_before_review
        human_agrees = dec.decision == "approve"
        if human_agrees and agent_conf < 0.4:
            if not dec.reason_text:
                result.add_error(artifact_path, "reason_text",
                                 "Confidence/decision conflict requires reason text")
        elif not human_agrees and agent_conf >= 0.85:
            if not dec.reason_text:
                result.add_error(artifact_path, "reason_text",
                                 "Confidence/decision conflict requires reason text")
