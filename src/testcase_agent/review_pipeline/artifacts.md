# Review Pipeline Artifacts (Simplified A/B/C Pipeline)

## JSON Source-of-Truth Rule

JSON is the source of truth. Each LLM output artifact and its `reviewed_*` counterpart
use the same schema.

## Artifact Catalog

### `00_requirements.json` (input)
Produced by: External (Excel import or hand-authored).
Consumed by: `extract` (LLM-A).

### `extracted_test_basis.json`
Produced by: `extract` (LLM-A).
Consumed by: Human reviewer.

Five evidence sections: signals, thresholds, timing, states, observations.
Each item has status (`known` or `needs_review`), content, need, and source_text.
May have `blocking_gaps` if the requirement is non-testable.

### `reviewed_extracted_test_basis.json`
Produced by: Human reviewer (Accept All, Edit, Add, Remove, or Block Run).
Consumed by: `plan-intents` (LLM-B).

Same schema as `extracted_test_basis.json`. Downstream stages read only this
reviewed artifact, never the raw LLM-A output.

### `case_intents.json`
Produced by: `plan-intents` (LLM-B).
Consumed by: Human reviewer.

Coverage plan: list of `{intent_id, coverage_dimension, intent_text}`.
No confidence routing, reasons, or item-level basis references.

### `reviewed_case_intents.json`
Produced by: Human reviewer (Accept All, Edit, Add, Remove, or Block Run).
Consumed by: `generate-cases` (LLM-C).

Same schema as `case_intents.json`.

### `generated_cases.json`
Produced by: `generate-cases` (LLM-C).
Consumed by: Human reviewer.

`GeneratedCaseSet` with `cases` list. Same object schema as `reviewed_cases.json`.

### `reviewed_cases.json`
Produced by: Human reviewer (Accept All, Edit, or Regenerate).
Consumed by: Results/export.

Same schema as `generated_cases.json`. Downstream consumers prefer this file
when it exists.

## Review Actions

### Extraction & Intents (A/B stages)
`accept` | `edit` | `add` | `remove` | `block`

Block Run records a `blocking_gaps` entry. Blocking gaps stop all downstream
stages. Accept All cannot bypass blocking gaps.

### Cases (C stage)
`accept` | `edit` | `regenerate`

C review does not support Remove or Block Run.
Regenerate uses reviewed artifacts and a human review comment.

## Blocking Gaps

When a reviewed artifact has non-empty `blocking_gaps`, all downstream stages
must stop and surface the blocked status with reasons.

## Legacy Artifacts

The following are from the legacy facts/ambiguities pipeline and are NOT
supported by the simplified pipeline:
- `clarification_review.json`
- `clarified_test_basis.json`
- `case_intent_review.json`
- `approved_case_plan.json`

Legacy run directories must be regenerated through the new artifact flow.
