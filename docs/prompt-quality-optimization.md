# Prompt Quality Optimization

**Status:** draft
**Date:** 2026-05-19

Workflow source of truth: `.claude/skills/optimize-prompt-by-checklist/skill.md`. This document owns
the quality strategy, rubric, and Prompt Evaluation Set rationale. Use the
workflow document for current commands, CLI selection semantics, checklist
version, evaluator ownership, and run procedure.

## Goal

Improve BMS HIL test case quality from a local 7B-8B model, with special
focus on reducing hallucinated signals, thresholds, timing, states, and
observation points.

The primary quality risk is not malformed HTML. The primary quality risk is a
case that looks executable while inventing requirement semantics that were not
provided by the source requirement.

## Evaluation Strategy

Prompt changes are evaluated with one stable requirement set:

- **Prompt Evaluation Set**: a fixed requirement set used as the primary
  quality benchmark for prompt changes.

Random sampling may still be used for exploration, but it is not the primary
acceptance signal for prompt quality.

The Prompt Evaluation Set is not a set of reference test cases. It is a fixed
set of source requirements used to generate and compare test cases across
prompt versions.

Current workflow details are documented in `.claude/skills/optimize-prompt-by-checklist/skill.md`.

## Manual Review Rubric

Each requirement group in the Prompt Evaluation Set receives an 8-dimension
review score from 1 to 5.

`coverage_value` is requirement-level: it evaluates the full set of generated
cases for one requirement. The other seven dimensions are case-level and are
averaged within the requirement before computing the weighted score.

| Criterion | Level | Weight | Meaning |
| --- | --- | ---: | --- |
| Requirement Alignment | Case | 20% | The case tests the intended requirement without drifting to unrelated BMS behavior. |
| Information Integrity | Case | 20% | Concrete signals, thresholds, timings, states, observations, diagnostics, bus messages, HIL channels, and tool commands are supported by the test basis or marked `[NEEDS REVIEW]` when missing. |
| Executability | Case | 15% | A HIL engineer or automation script can execute the procedure without rewriting the case. |
| Observability | Case | 15% | Expected results point to observable evidence from BMS outputs, diagnostics, logs, traces, or measurements. |
| Pass/Fail Clarity | Case | 10% | Recorded evidence can be judged objectively as pass or fail. |
| Coverage Value | Requirement | 10% | The full case set provides meaningful, complementary requirement coverage. |
| State & Environment Control | Case | 5% | Initial state, environment assumptions, transitions, restore/reset behavior, and postconditions are controlled. |
| Automation Readiness | Case | 5% | The case is structured, atomic, and consistent enough for downstream script or test-asset conversion. |

Weighted scores are computed per requirement, then averaged across requirements.
This prevents a requirement with many generated cases from dominating the
run-level score.

Hard gates remain separate from weighted scoring:

- If Information Integrity is lower than 3, the case is unacceptable.
- If a case should contain `[NEEDS REVIEW]` but does not, the case is
  unacceptable.
- If a case invents a missing signal, threshold, timing, state, or observation
  point, the case is unacceptable.
- If the requirement is semantically complete but the case adds unnecessary
  `[NEEDS REVIEW]`, the case is penalized but not automatically severe unless
  it blocks executability.

`[NEEDS REVIEW]` only covers requirement semantic gaps:

- `signal`
- `threshold`
- `timing`
- `state`
- `observation`

It does not cover HIL channel names, tool commands, bench configuration, or
other execution-environment details.

Current status: Phase 4 is complete and the rubric has been upgraded to 8
dimensions. Manual review scores are loaded from `manual_review_scores.json`,
weighted, hard-gated, and rendered in the report alongside (but separate from)
the automated checklist pass rate.

See `optimization/manual_review.py` for the implementation.

## Prompt Evaluation Set V1

Prompt Evaluation Set V1 is selected from the existing 64-requirement
evaluation pool in `optimization_runs/log/20260519_v2-full64_evalonly/`.

The machine-readable source of truth is
`optimization_runs/requirement_sets/prompt_eval_v1.json`. The Markdown tables
below are human-readable documentation and should stay in sync with the JSON.

Run commands and CLI selection semantics are documented in
`.claude/skills/optimize-prompt-by-checklist/skill.md`.

### Complete Information Baseline

Purpose: confirm that the model does not add unnecessary `[NEEDS REVIEW]` when
the requirement gives enough semantic information.

| Requirement | Function | Expected missing categories |
| --- | --- | --- |
| REQ-BMS-OVP-002 | Overvoltage Protection | none |
| REQ-BMS-OVP-009 | Overvoltage Protection | none |
| REQ-BMS-ISO-002 | Insulation & HVIL | none |
| REQ-BMS-COM-004 | Communication & Diagnostics | none |
| REQ-BMS-STM-002 | BMS State Machine | none |

### Threshold, Timing, and Boundary Cases

Purpose: stress numeric hallucination, symbolic parameter usage, boundary
splitting, and wait/verify separation.

| Requirement | Function | Expected missing categories |
| --- | --- | --- |
| REQ-BMS-OVP-001 | Overvoltage Protection | timing |
| REQ-BMS-OVP-003 | Overvoltage Protection | none |
| REQ-BMS-OVP-006 | Overvoltage Protection | none |
| REQ-BMS-CUR-001 | Current Management | none |
| REQ-BMS-CUR-002 | Current Management | timing |
| REQ-BMS-CUR-003 | Current Management | none |
| REQ-BMS-CUR-004 | Current Management | none |
| REQ-BMS-UVP-001 | Undervoltage Protection | threshold, timing |
| REQ-BMS-UVP-002 | Undervoltage Protection | timing |
| REQ-BMS-UVP-003 | Undervoltage Protection | threshold, timing |
| REQ-BMS-COM-003 | Communication & Diagnostics | none |
| REQ-BMS-CHG-002 | Charge Management | timing |
| REQ-BMS-THM-001 | Thermal Management | timing, observation |
| REQ-BMS-THM-006 | Thermal Management | timing |

### Missing Information Traps

Purpose: verify that missing requirement semantics are detected and represented
with a bare `[NEEDS REVIEW]` marker in the generated case.

| Requirement | Function | Expected missing categories |
| --- | --- | --- |
| REQ-BMS-THM-004 | Thermal Management | threshold, timing |
| REQ-BMS-PVP-001 | Pack Voltage Protection | threshold, timing |
| REQ-BMS-DEG-001 | Degradation Monitoring | threshold, observation |
| REQ-BMS-STM-003 | BMS State Machine | timing |
| REQ-BMS-STM-005 | BMS State Machine | timing |
| REQ-BMS-BAL-002 | Cell Balancing | threshold, timing |
| REQ-BMS-CUR-005 | Current Management | timing |
| REQ-BMS-ISO-003 | Insulation & HVIL | timing |

### Multi-Branch and Multi-Mode Cases

Purpose: verify that the legacy analysis stage split case intents without
merging independent branches, modes, or outcomes.

| Requirement | Function | Expected missing categories |
| --- | --- | --- |
| REQ-BMS-THM-007 | Thermal Management | timing |
| REQ-BMS-CHG-001 | Charge Management | observation |
| REQ-BMS-CHG-004 | Charge Management | state, observation |
| REQ-BMS-STM-004 | BMS State Machine | timing |

### State, Observation, and Diagnostic Cases

Purpose: verify extraction and use of BMS states, DTCs, logged records, CAN
messages, fault records, and observable diagnostic outputs.

| Requirement | Function | Expected missing categories |
| --- | --- | --- |
| REQ-BMS-OVP-004 | Overvoltage Protection | timing |
| REQ-BMS-BAL-003 | Cell Balancing | observation |
| REQ-BMS-FLT-001 | Fault Management | timing |
| REQ-BMS-STM-006 | BMS State Machine | state, timing |

## Prompt and Pipeline Scope

Status as of 2026-05-24: this document describes the legacy prompt optimization
workflow used before the clarification-first review pipeline. It remains useful
for interpreting old `optimization_runs` reports, but it is no longer the
current generation entry point.

Current generation starts with:

```text
python -m testcase_agent.review_pipeline.cli prepare-clarification-review
```

Current prompts live under `src/testcase_agent/review_pipeline/prompts/`:

- `decompose_requirement.system.html`
- `decompose_requirement.user.html`
- `plan_case_intents.system.html`
- `plan_case_intents.user.html`
- `write_case.system.html`
- `write_case.user.html`

The old root prompt files and the old `analyze_and_plan -> generate_case`
pipeline have been removed. `self_check` is out of scope for phase 1.

Legacy note: in the archived two-call optimization workflow, LLM#1 was
responsible for requirement analysis and case intent planning. That stage was
extended to extract:

- `extracted_states`
- `extracted_observations`
- categorized `missing_critical_info` items, using `category="signal"`,
  `category="threshold"`, `category="timing"`, `category="state"`, or
  `category="observation"`

Legacy LLM#2 wrote one test case for one case intent. It received known states
and observation points from LLM#1, and it had fallback authority to place
`[NEEDS REVIEW]` when it discovered a required semantic gap that LLM#1 missed.

In both legacy reports and the current review pipeline, generated cases show
only the literal marker `[NEEDS REVIEW]`. Missing information categories remain
internal analysis/review metadata.

Current status: Phase 1 (Data Channel) is complete.

- Parser, pipeline, and prompt templates carried `extracted_states`,
  `extracted_observations`, and categorized `missing_critical_info` from
  legacy analysis into legacy case writing.
- Legacy `optimization/cli.py run` persisted all new analysis metadata in
  `generated_cases.json`. That generation command has now been removed.
- The legacy `strip_needless_markers()` path that unconditionally stripped
  `[NEEDS REVIEW]` when analysis reported no missing information was removed
  from the old CLI path; case-writer fallback `[NEEDS REVIEW]` markers were
  preserved.

## Compatibility Requirements

Parser and pipeline changes must remain compatible with older optimization
logs and older prompt output:

- Missing `extracted_states` or `extracted_observations` sections parse as
  empty lists.
- Old missing-info format remains valid:
  `<item>response timing not specified</item>`.
- New missing-info format is supported:
  `<item category="timing">response timing not specified</item>`.
- Existing generated case parsing remains unchanged.

## Checklist Updates

Target: `optimization_runs/checklist_v2.md`, the automated evaluator, and the
HTML reports should all treat missing information detection as a hard quality
gate.

Recommended legacy checklist changes:

- Replace the current broad `[NEEDS REVIEW]` usage rule with checks that
  distinguish omitted markers from unnecessary markers.
- Require the analysis stage to identify semantic gaps using one of the five
  canonical categories when the source requirement lacks needed semantics.
- Require generated action or expected fields to contain a bare
  `[NEEDS REVIEW]` where a missing semantic value is actually needed.
- Forbid placing `[NEEDS REVIEW]` in unrelated title, objective, precondition,
  or postcondition fields.

Current status: Phase 3 (Hard-Gate Evaluation) is complete. The automated
evaluator and reports now include v2 Section 3 hard-gate items and a
Missing Information Hard Gates section that compares Prompt Evaluation Set
expected categories against legacy analysis output.

Remaining gap: automated detection of 3.2.2 (invented semantics) is limited to
threshold/pattern matching. Full detection of invented signals, states, and
observations requires semantic review (Phase 4).

## Implementation Plan

### Phase 1: Data Channel ✅

Completed 2026-05-19.

Goal: make legacy analysis metadata available to case writing and downstream
reports.

Completed work:

- Parse states, observations, and categorized missing information.
- Pass states, observations, and categorized missing information into case
  writing.
- Persist states, observations, and categorized missing information in
  `generated_cases.json`.
- Keep old prompt output compatible.
- Remove unconditional `strip_needless_markers()` path that conflicted with
  case-writer fallback authority.

### Phase 2: Prompt Evaluation Set Execution ✅

Completed 2026-05-19.

Goal: make Prompt Evaluation Set V1 executable instead of relying on random
sampling.

Completed work:

- Store Prompt Evaluation Set V1 in a machine-readable artifact
  (`optimization_runs/requirement_sets/prompt_eval_v1.json`).
- Add an executable fixed-set path to legacy `optimization.cli run`; this
  command has since been removed from active generation by ADR-0003.
- Validate that all listed Requirement IDs exist in the source Excel.
- Validate no duplicate keys, valid expected_missing_categories.
- Save the set name, path, and entry count in `summary.json`.
- Enrich `generated_cases.json` entries with `evaluation_bucket`,
  `expected_missing_categories`, and `requirement_set_note`.
- Preserve random exploration as a separate CLI mode.
- Current CLI selection semantics are documented in
  `.claude/skills/optimize-prompt-by-checklist/skill.md`.

### Phase 3: Hard-Gate Evaluation ✅

Completed 2026-05-19.

Goal: align the automated evaluator and reports with the missing-information
quality policy.

Completed work:

- Synchronized evaluator `CHECKLIST` with `checklist_v2.md` Section 3
  (6 new/replaced items: 3.2.1 [HARD], 3.2.2 [HARD], 3.2.3 [WARNING],
  3.3.1, 3.3.2, 3.3.3).
- `evaluate_case()` now accepts `expected_missing_categories` from Prompt
  Evaluation Set metadata and returns `(failed, warnings)` tuple.
- `evaluate_missing_info_hard_gates()` compares expected vs actual missing
  categories and detects case-level [NEEDS REVIEW] gaps.
- `cases_report.html` includes hard-gate evaluation (3.2.x items) per case with
  evaluator badge cards, and displays `evaluation_bucket`, expected/actual missing
  categories, states, and observations per requirement.
- 26 new evaluator tests covering all 3.x items and hard gate logic.
- WARNING items (3.2.3, 4.1.1) are tracked separately and do not count toward
  pass/fail.

### Phase 4: Manual Review Score ✅

Completed 2026-05-19.
Updated to the 8-dimension rubric on 2026-05-20.

Goal: capture the human review rubric as structured data.

Completed work:

- Defined `manual_review_scores.json` as the review input format. Each
  requirement entry has `requirement_key`, requirement-level `coverage_value`,
  and a `cases` array with 0-based `case_index` plus the seven case-level
  scores. Optional `reviewer` and `notes` are supported at requirement and case
  level. See `optimization/manual_review.py`.
- Weighted score formula: 20% requirement_alignment + 20%
  information_integrity + 15% executability + 15% observability + 10%
  pass_fail_clarity + 10% coverage_value + 5%
  state_and_environment_control + 5% automation_readiness. Per-requirement
  scores are rounded to 1 decimal for reporting.
- Hard gates applied before accepting any weighted score:
  `information_integrity < 3` → unacceptable; expected missing
  categories but no `[NEEDS REVIEW]` in case → unacceptable; invented
  numeric values for missing semantics → unacceptable; unnecessary
  `[NEEDS REVIEW]` → warning (not automatically severe).
- Manual Review hard gates reuse the shared evaluator logic.
- Manual Review Scores section rendered in `evaluation_report.html` and `cases_report.html` alongside
  but separate from automated checklist pass rate. Shows average weighted score,
  dimension averages/minimums, requirement-level score distribution,
  unacceptable cases, and scored case detail table. When
  `manual_review_scores.json` is absent, the section is omitted (no error).
- 29 tests covering weighted score computation, hard gates, file validation,
  review summary aggregation, and report HTML rendering.

## Acceptance Criteria

For legacy reports, the archived optimization workflow was acceptable when:

- Parser tests cover old and new missing-info formats.
- Legacy pipeline output carried states and observations from analysis into
  case writing.
- Prompts kept the old two-call architecture: analyze-and-plan first, one-case
  generation second. This is no longer the active generation architecture.
- Prompt Evaluation Set V1 can be run without random sampling.
- Prompt Evaluation Set reports severe missing-info failures
  explicitly.
- Manual Review Scores can be recorded and weighted separately from automated
  checklist pass rate.
- Prompt changes do not improve scores merely by reducing case count,
  overusing `[NEEDS REVIEW]`, or avoiding concrete expected results.

## Out of Scope

- These legacy out-of-scope items were superseded by ADR-0003. The active
  pipeline uses JSON artifacts as the source of truth and a three-stage
  clarification-first LLM flow.
- Adding HIL bench command generation.
- Treating tool commands, HIL channels, or bench configuration as
  `[NEEDS REVIEW]` semantics.
