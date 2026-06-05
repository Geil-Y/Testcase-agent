# ADR-0007: Review Feedback Loop — Accept / Edit / Regenerate

**Date:** 2026-06-05
**Status:** Accepted

## Context

ADR-0005 defined a three-stage review pipeline (LLM-A → LLM-B → LLM-C) with
review actions: Accept, Edit, Add, Remove, Block Run. In the Pipeline Console
implementation (ADR-0006), review was reduced to a simple gate: the human
inspected LLM output, made optional edits, and clicked "Advance" to proceed.
Human feedback never fed back into LLM re-generation — the Regenerate buttons
in the UI were visual-only with no API wiring.

This made the `review_required` configuration meaningless: selecting review for
a stage only paused the pipeline; it did not enable any feedback mechanism.
Human review did not participate in LLM decision-making.

## Decision

Replace the gate-only review model with an interactive feedback loop centered
on three canonical actions:

| Action | Scope | Effect |
|---|---|---|
| **Edit** | LLM-A per-item, LLM-B per-intent, LLM-C per-case | Human directly modifies content in-place. Edited content carries the same authority as Accepted content. |
| **Regenerate** | LLM-A per-item, LLM-B whole-plan, LLM-C none | Human writes a mandatory Review Comment explaining the deficiency. The same LLM re-produces output with the comment injected as structured priority guidance in the prompt. |
| **Accept** | Whole-stage (all three stages) | Human confirms the entire stage output as authoritative. Locks all items. Required before Stage Advance. Reversible via Unlock. |

Key design decisions:

- **Structured prompt injection for Regenerate.** Dedicated prompt files
  (`prompts/regenerate_test_basis_item.*.md`, `prompts/regenerate_case_intents.*.md`)
  receive the original output, the human comment with explicit priority markers,
  and the original requirement context. The comment is not appended to the
  original prompt — it is injected with structured markup so the 7B/8B model
  can clearly distinguish human authority from its own prior inference.

- **Whole-stage Accept, not per-item.** Accept is a milestone decision ("I'm
  done reviewing this stage") rather than a per-item approval. This keeps the
  workflow lightweight: the human edits or regenerates individual items as
  needed, then makes one final Accept decision.

- **Accept locks; Unlock reverts.** After Accept, all items in that stage are
  frozen. A dedicated Unlock button reverses Accept. Unlocking an upstream
  stage (e.g. LLM-A) when downstream data exists (LLM-B intents, LLM-C cases)
  triggers a confirmation dialog warning of cascade invalidation.

- **Cascade invalidation on upstream change.** When LLM-A items are modified
  or regenerated after downstream stages have run, all LLM-B intents and LLM-C
  cases are marked stale and must be regenerated. LLM-B intents that were
  previously Accepted (in a prior round) are preserved as positive examples
  for the re-run.

- **Regenerate has a 3-attempt cap (LLM-B only).** LLM-B whole-plan Regenerate
  is limited to 3 attempts per Run. On the 4th attempt, the stage enters Force
  Edit state: Regenerate is disabled, the human must manually edit or delete
  intents. LLM-A Regenerate has no cap initially (expected low usage); caps may
  be added later if usage patterns warrant.

- **LLM-B intent history preserved.** Each Regenerate creates a new version
  (`case_intents.version`). The UI provides a version history viewer so the
  human can compare past plans.

- **`review_required` semantic unchanged.** Stages not in `review_required`
  are auto-accepted: their LLM output passes through without human interaction.
  Stages in `review_required` follow the full Accept/Edit/Regenerate workflow.

- **LLM-C has no Regenerate.** LLM-C review is Edit + Accept only. If a case
  needs full regeneration, the human should go back to LLM-B (or LLM-A) and
  advance forward again.

## Rationale

- The original gate-only model was a side effect of Console MVP prioritization:
  wiring up review actions was deferred to ship the pipeline UI. This ADR
  closes that gap explicitly rather than patching around it.
- Structured prompt injection over appending: the 7B/8B model struggles with
  high-density prompts. Clear section markers ("## Human Correction", "##
  Previous Output") reduce the chance the model ignores the human comment.
- Whole-stage Accept over per-item Accept: the test basis and intent plan are
  small enough (typically 5-20 items) that per-item Accept adds click fatigue
  without meaningful safety gain.
- 3-attempt cap on LLM-B: prevents infinite re-generation loops. If the LLM
  cannot satisfy the human after 3 attempts with explicit feedback, the problem
  is likely in the requirement itself or beyond the model's capability — human
  editing is more efficient.
- Cascade invalidation is safer than partial staleness tracking: with a 7B
  model, any upstream change can affect any downstream output through the
  prompt context; partial tracking would miss cross-item dependencies.

## Consequences

- **Database schema**: `test_basis_items` and `case_intents` gain 4 fields:
  `review_status`, `review_comment`, `regenerate_count`, `accepted_at`.
  `runs` gains `llm_a_accepted` and `llm_b_accepted` boolean columns.
  `case_intents` gains a `version` integer column for history.
- **New prompt files**: `prompts/regenerate_test_basis_item.system.md`,
  `prompts/regenerate_test_basis_item.user.md`,
  `prompts/regenerate_case_intents.system.md`,
  `prompts/regenerate_case_intents.user.md`.
- **New API endpoints**: Regenerate for LLM-A items and LLM-B plan, Unlock for
  each stage, version history for LLM-B intents.
- **Frontend**: Accept/Unlock buttons per stage, Regenerate button with comment
  input, Force Edit state indicator, version history viewer for LLM-B,
  cascade invalidation confirmation dialog.
- **State machine**: Each stage tracks `pending → accepted` (or `pending →
  regenerating → pending` loop with counter, then `force_edit → accepted`).
  Advance requires `accepted`.
- **ADR-0005** review actions (Accept, Edit, Add, Remove, Block Run) are
  superseded by the Accept/Edit/Regenerate model. Block Run and Add are
  deferred — not implemented in this change.

## Considered Options

- **Per-item Accept**: rejected — adds click fatigue without proportional
  safety gain for small item sets.
- **Appending comment to original prompt (no structured injection)**:
  rejected — 7B/8B model performance degrades with long, unstructured prompts.
- **No cascade invalidation (manual downstream re-trigger)**: rejected — risks
  stale downstream data being silently accepted as authoritative.
- **Unlimited Regenerate attempts**: rejected — infinite loops waste human
  time when the LLM cannot converge.
- **LLM-C Regenerate**: rejected — LLM-C output depends on LLM-A and LLM-B
  inputs; if a case is wrong, the root cause is upstream, and regenerating
  the same case from unchanged inputs would produce the same result.
