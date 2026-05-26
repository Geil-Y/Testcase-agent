"""Issue 7: Clarification review validation and clarified test basis.

Validates human-edited clarification_review.json and produces
clarified_test_basis.json for the case intent planner.
"""

from __future__ import annotations

from pathlib import Path

from review_pipeline.artifacts.io import read_json, write_json
from review_pipeline.artifacts.models import (
    ClarificationReview,
    ClarificationDecision,
    ClarifiedTestBasis,
)
from review_pipeline.artifacts.validation import ValidationResult
from review_pipeline.reason_codes import (
    is_decision_valid,
    is_reason_code_valid,
    get_decision_requirements,
    requires_reason_text_on_conflict,
)


def validate_clarification_review(file_path: str) -> tuple[ValidationResult, ClarifiedTestBasis | None]:
    """Validate a human-edited clarification review JSON and produce clarified test basis."""
    result = ValidationResult()
    data = read_json(file_path)
    review = ClarificationReview(**data)

    # Validate each decision
    has_block = False
    block_reasons: list[str] = []
    resolved_ambiguities: list[dict] = []
    ambiguity_by_id = {a.item_id: a for a in review.decomposition.ambiguities}

    for dec in review.decisions:
        _validate_clarification_decision(dec, review, result)
        if dec.decision == "block":
            has_block = True
            block_reasons.append(dec.reason_text or f"Blocked: {dec.item_id}")

        # Collect resolved ambiguity info
        ambiguity = ambiguity_by_id.get(dec.item_id)
        resolved_ambiguities.append({
            "item_id": dec.item_id,
            "decision": dec.decision,
            "ambiguity_type": ambiguity.ambiguity_type if ambiguity else "",
            "affected_text": ambiguity.affected_text if ambiguity else "",
            "clarified_value": dec.clarified_value,
            "reason_codes": dec.reason_codes,
        })

    if result.errors:
        return result, None

    # Build clarified test basis
    basis = ClarifiedTestBasis(
        requirement_key=review.requirement_key,
        review_session_id=review.review_session_id,
        source_description=review.source_description,
        function_name=review.function_name,
        requirement_type=review.requirement_type,
        supplementary_info=review.supplementary_info,
        test_basis_hash=_hash_basis(review),
        facts=review.decomposition.facts,
        resolved_ambiguities=resolved_ambiguities,
        blocked=has_block,
        block_reasons=block_reasons,
    )

    # Write clarified test basis alongside the review file
    run_dir = Path(file_path).parent
    write_json(run_dir / "clarified_test_basis.json", basis.model_dump())

    return result, basis


def _validate_clarification_decision(
    dec: ClarificationDecision, review: ClarificationReview, result: ValidationResult
) -> None:
    artifact_path = f"clarification_review.json / decisions / {dec.item_id}"

    if not is_decision_valid("clarification_item", dec.decision):
        result.add_error(artifact_path, "decision", f"Unknown decision: {dec.decision}")
        return

    reqs = get_decision_requirements(dec.decision)

    # Non-approve decisions require reason codes
    if reqs.get("require_reason_code") and not dec.reason_codes:
        result.add_error(artifact_path, "reason_codes",
                         f"Decision '{dec.decision}' requires at least one reason code")
    else:
        for rc in dec.reason_codes:
            if not is_reason_code_valid("clarification_item", rc):
                result.add_error(artifact_path, "reason_codes", f"Unknown reason code: {rc}")

    # Some decisions require reason text
    if reqs.get("require_reason_text") and not dec.reason_text:
        result.add_error(artifact_path, "reason_text",
                         f"Decision '{dec.decision}' requires reason text")

    # Decision-specific validation
    if dec.decision == "clarify" and not dec.clarified_value:
        result.add_error(artifact_path, "clarified_value",
                         "Decision 'clarify' requires clarified value")

    if dec.decision == "edit" and not dec.edited_content:
        result.add_error(artifact_path, "edited_content",
                         "Decision 'edit' requires edited content")

    # Confidence/decision conflict check
    if dec.confidence_before_review is not None and requires_reason_text_on_conflict():
        agent_conf = dec.confidence_before_review
        # For simplicity, we assume approve means human agrees
        human_agrees = dec.decision == "approve"
        if human_agrees and agent_conf < 0.4:
            if not dec.reason_text:
                result.add_error(artifact_path, "reason_text",
                                 "Confidence/decision conflict requires reason text")
        elif not human_agrees and agent_conf >= 0.85:
            if not dec.reason_text:
                result.add_error(artifact_path, "reason_text",
                                 "Confidence/decision conflict requires reason text")


def _hash_basis(review: ClarificationReview) -> str:
    import hashlib
    content = review.requirement_key + review.source_description + "|".join(
        f.item_id for f in review.decomposition.facts
    ) + "|".join(
        d.item_id + d.decision for d in review.decisions
    )
    return hashlib.sha256(content.encode()).hexdigest()[:16]
