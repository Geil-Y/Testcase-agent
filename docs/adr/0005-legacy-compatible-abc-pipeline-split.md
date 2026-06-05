# ADR-0005: Legacy-Compatible A/B/C Pipeline Split

**Date:** 2026-05-28
**Status:** Accepted

## Context

The legacy pipeline used two LLM responsibilities:

```
analyze_and_plan -> generate_case
```

The first call both extracted concrete requirement evidence and planned case
intents. The second call wrote one test case from the current intent, original
requirement description, extracted sections, and missing-information list.

ADR-0003 introduced a clarification-first review pipeline centered on facts,
ambiguities, confidence routing, and human decisions. In practice this model
overloaded the pipeline data model and weakened generated first-draft case
quality because the case writer no longer received the legacy-style structured
sections it needs.

## Decision

Use a legacy-compatible three-stage split:

```
LLM-A extraction -> review -> LLM-B planning -> review -> LLM-C case writing -> review
```

LLM-A extracts only five concrete evidence sections and missing needs from the
requirement description:

- signals
- thresholds
- timing
- states
- observations

LLM-A does not plan case count, coverage dimensions, or case intents.

The extracted test basis uses a minimal schema:

- `sections`: five named lists for signals, thresholds, timing, states, and
  observations.
- section item: `item_id`, `status` (`known` or `needs_review`), `content`,
  `need`, and `source_text`.
- `blocking_gaps`: reasons the requirement cannot safely proceed because the
  testable behavior is unclear or non-testable.

LLM-B plans case intents from the requirement description and reviewed extracted
sections. It decides coverage dimensions and case count.

LLM-C writes one test case from the original requirement description, the
current approved intent, all reviewed extracted sections, and unresolved missing
items. This matches the legacy LLM2 input pattern.

Supplementary info is not passed to LLM-A, LLM-B, or LLM-C. It may be shown to
human reviewers later as reference only.

Review remains part of the pipeline:

- LLM-A output review covers extracted sections and missing items.
- LLM-B output review covers planned case intents.
- LLM-C output review covers generated test cases.

LLM-A and LLM-B review actions are intentionally simple:

- Accept keeps an item for the next stage. Accepting an unresolved item keeps
  its `[NEEDS REVIEW]` obligation.
- Edit changes a known item or resolves an unresolved item with human-provided
  content.
- Add creates an item or intent that the LLM missed.
- Remove deletes an item from the reviewed output.
- Block Run records that the requirement cannot safely proceed because the
  testable behavior is unclear or non-testable.

LLM-C review is case-text focused:

- Accept keeps the generated case.
- Edit lets a human directly revise the generated case.
- Regenerate reruns LLM-C for the same approved intent with a human review
  comment.

LLM-C review does not remove cases or block the run. If a case should not exist,
the reviewer should go back to LLM-B intent review. If generation is unsafe, the
reviewer should go back to LLM-A extraction review or LLM-B intent review.
Regenerate comments may guide wording, structure, and use of already approved
materials, but they must not introduce new concrete identifiers, thresholds,
timing, states, observations, or new case intent outside the reviewed extraction
and approved intent.
LLM-C regeneration always uses reviewed artifacts
(`reviewed_extracted_test_basis.json` and `reviewed_case_intents.json`) plus the
review comment; it must not read unreviewed LLM-A or LLM-B outputs.

The first implementation stores the reviewed state, not the action history.
Accept/Edit/Add/Remove are UI concepts reflected by the resulting artifact
content. Audit history may be added later if review workflows require it.

Stage artifacts are named by content. Reviewed artifacts use the `reviewed_`
prefix:

- LLM-A output: `extracted_test_basis.json`
- Reviewed LLM-A output: `reviewed_extracted_test_basis.json`
- LLM-B output: `case_intents.json`
- Reviewed LLM-B output: `reviewed_case_intents.json`
- LLM-C output: `generated_cases.json`
- Reviewed LLM-C output: `reviewed_cases.json`

The previous `clarification_review.json` / `clarified_test_basis.json` naming
no longer matches the simplified extraction model.
Each LLM output artifact and its reviewed counterpart use the same schema; the
reviewed artifact is the human-edited, downstream-authoritative version.
Downstream stages read only reviewed artifacts. Continuing without manual edits
requires an explicit Accept All action that writes the reviewed artifact; stages
must not silently treat unreviewed LLM output as reviewed.
When a reviewed artifact contains `blocking_gaps`, downstream stages must stop
and surface the blocked status and reasons. Accept All must not bypass blocking
gaps; a reviewer must edit or remove the blocking gaps before continuing.

Existing run directories with legacy artifacts such as `clarification_review.json`
or `clarified_test_basis.json` are not migrated in place. They are unsupported by
the simplified pipeline and should be regenerated through the new artifact flow.

This ADR supersedes the facts/ambiguities-centric data model from ADR-0003 while
preserving the clarification-first, human-reviewable principle.

## Rationale

- The original LLM1 did two jobs. Splitting it into extraction and planning
  keeps each small-model call narrower without changing the successful data
  shape consumed by the case writer.
- The case writer needs explicit known signals, thresholds, timing, states, and
  observations. Free-text facts and ambiguity narratives are too weak and
  increase hallucination risk.
- Missing-information detection should happen in LLM-A and human review. LLM-B
  and LLM-C may propagate unresolved missing items, but must not invent new
  missing information or add new review markers on their own.
- Avoiding item-level references, confidence routing, and complex review
  metadata in the first simplification keeps the pipeline closer to the legacy
  prompt behavior and reduces local-model burden.

## Consequences

- `RequirementDecomposition` should be replaced by the extracted sections and
  missing-items model rather than preserved through a compatibility layer.
- `ClarifiedTestBasis` should be replaced by
  `reviewed_extracted_test_basis.json`, which carries reviewed extracted
  sections and unresolved missing items as generation authority.
- LLM-B prompts should focus on coverage and intent planning, not extraction.
- LLM-C prompts should restore the legacy known-section inputs and use
  unresolved missing items as the only source of `[NEEDS REVIEW]` markers.
- Existing facts/ambiguities/confidence-routing fields should be removed from
  the main review-pipeline model during migration. Tests and Console behavior
  should be updated to the new model instead of preserving the old structure.
- Validation that edited/generated cases only use reviewed extraction materials
  is a later quality-gate concern and is not part of the first simplification.
- Review Memory is removed from the main pipeline path during this migration.
  It may be redesigned later around reviewed artifacts instead of legacy
  ambiguity decisions, reason codes, and pattern tags.
