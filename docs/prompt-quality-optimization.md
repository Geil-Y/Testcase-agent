# Prompt Quality Optimization

**Status:** draft
**Date:** 2026-05-19

## Goal

Improve BMS HIL test case quality from a local 7B-8B model, with special
focus on reducing hallucinated signals, thresholds, timing, states, and
observation points.

The primary quality risk is not malformed HTML. The primary quality risk is a
case that looks executable while inventing requirement semantics that were not
provided by the source requirement.

## Evaluation Strategy

Prompt changes are evaluated with one stable requirement set:

- **Prompt Evaluation Set**: 30 fixed requirements used as the primary quality
  benchmark for prompt changes.

Random sampling may still be used for exploration, but it is not the primary
acceptance signal for prompt quality.

The Prompt Evaluation Set is not a set of reference test cases. It is a fixed
set of source requirements used to generate and compare test cases across
prompt versions.

Current status: Prompt Evaluation Set V1 is machine-readable and can be run by
`optimization/cli.py` with `--requirement-set`. Random sampling remains
available for exploration, but it is no longer the only CLI path.

## Manual Review Rubric

Each generated case in the Prompt Evaluation Set receives four human scores
from 1 to 5:

| Criterion | Weight | Meaning |
| --- | ---: | --- |
| Executability | 20% | A HIL engineer can execute the procedure without rewriting the case. |
| Observability | 20% | Expected results are concrete and judgeable from BMS outputs. |
| Coverage Value | 20% | The case verifies a meaningful requirement behavior or risk. |
| Missing Information Detection | 40% | The case identifies requirement semantic gaps instead of inventing values or behavior. |

Hard gates:

- If Missing Information Detection is lower than 3, the case is unacceptable.
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

Current status: this rubric is a manual review policy. The repository does not
yet provide score input files, weighted score calculation, or report rendering
for these four scores.

## Prompt Evaluation Set V1

These 30 requirements are selected from the existing 64-requirement evaluation
pool in `optimization_runs/log/20260519_v2-full64_evalonly/`.

The machine-readable source of truth is
`optimization_runs/requirement_sets/prompt_eval_v1.json`. The Markdown tables
below are human-readable documentation and should stay in sync with the JSON.

The set is executable via:
```
python -m optimization.cli run \
  --excel requirements.xlsx \
  --requirement-set optimization_runs/requirement_sets/prompt_eval_v1.json \
  --output-dir ...
```

### Complete Information Baseline

Purpose: confirm that the model does not add unnecessary `[NEEDS REVIEW]` when
the requirement gives enough semantic information.

| Requirement | Function | Expected missing categories |
| --- | --- | --- |
| REQ-BMS-OVP-002 | Overvoltage Protection | none |
| REQ-BMS-OVP-009 | Overvoltage Protection | none |
| REQ-BMS-ISO-002 | Insulation & HVIL | none |
| REQ-BMS-ISO-004 | Insulation & HVIL | none |
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
| REQ-BMS-OVP-011 | Overvoltage Protection | none |
| REQ-BMS-CUR-001 | Current Management | none |
| REQ-BMS-CUR-004 | Current Management | none |
| REQ-BMS-COM-003 | Communication & Diagnostics | none |
| REQ-BMS-CHG-002 | Charge Management | timing |

### Missing Information Traps

Purpose: verify that missing requirement semantics are detected and represented
with a bare `[NEEDS REVIEW]` marker in the generated case.

| Requirement | Function | Expected missing categories |
| --- | --- | --- |
| REQ-BMS-THM-004 | Thermal Management | threshold, timing |
| REQ-BMS-THM-005 | Thermal Management | threshold, timing |
| REQ-BMS-PVP-001 | Pack Voltage Protection | threshold, timing |
| REQ-BMS-DEG-001 | Degradation Monitoring | threshold, observation |
| REQ-BMS-STM-003 | BMS State Machine | timing |
| REQ-BMS-STM-007 | BMS State Machine | timing |
| REQ-BMS-BAL-002 | Cell Balancing | threshold, timing |
| REQ-BMS-SOC-004 | SOC/SOH Estimation | threshold, timing |

### Multi-Branch and Multi-Mode Cases

Purpose: verify that LLM#1 splits case intents without merging independent
branches, modes, or outcomes.

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

LLM#1 remains responsible for requirement analysis and case intent planning.
It should be extended to extract:

- `extracted_states`
- `extracted_observations`
- categorized `missing_critical_info` items, using `category="signal"`,
  `category="threshold"`, `category="timing"`, `category="state"`, or
  `category="observation"`

LLM#2 remains responsible for writing one test case for one case intent. It
should receive known states and observation points from LLM#1, and it should
have fallback authority to place `[NEEDS REVIEW]` when it discovers a required
semantic gap that LLM#1 missed.

Generated cases still show only the literal marker `[NEEDS REVIEW]`. Missing
information categories remain internal analysis metadata.

Current status: Phase 1 (Data Channel) is complete.

- Parser, pipeline, and prompt templates all carry `extracted_states`,
  `extracted_observations`, and categorized `missing_critical_info` from LLM#1
  into LLM#2.
- `optimization/cli.py` persists all new analysis metadata in
  `generated_cases.json`.
- The legacy `strip_needless_markers()` path that unconditionally stripped
  `[NEEDS REVIEW]` when LLM#1 reported no missing information has been removed
  from the CLI; LLM#2 fallback `[NEEDS REVIEW]` markers are preserved.

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

Recommended changes:

- Replace the current broad `[NEEDS REVIEW]` usage rule with checks that
  distinguish omitted markers from unnecessary markers.
- Require LLM#1 to identify semantic gaps using one of the five canonical
  categories when the source requirement lacks needed semantics.
- Require generated action or expected fields to contain a bare
  `[NEEDS REVIEW]` where a missing semantic value is actually needed.
- Forbid placing `[NEEDS REVIEW]` in unrelated title, objective, precondition,
  or postcondition fields.

Current status: the checklist document has been partially updated, but the
automated evaluator and report generator still need to be synchronized with the
new hard-gate semantics.

Known gaps:

- `optimization/generate_case_html.py` does not yet fully represent the new
  hard-gate item IDs from `checklist_v2.md`.
- `evaluate_case()` does not yet compare expected missing categories from the
  Prompt Evaluation Set against actual LLM#1 missing information categories.
- `evaluate_case()` cannot reliably detect every case that should contain
  `[NEEDS REVIEW]` but does not; this requires Prompt Evaluation Set metadata
  plus semantic review.
- `optimization/generate_report.py` still reports checklist pass rate as the
  primary metric and does not render severe missing-information failures or
  Manual Review Scores.

## Implementation Plan

### Phase 1: Data Channel ✅

Completed 2026-05-19.

Goal: make LLM#1 analysis metadata available to LLM#2 and downstream reports.

Completed work:

- Parse states, observations, and categorized missing information.
- Pass states, observations, and categorized missing information into LLM#2.
- Persist states, observations, and categorized missing information in
  `generated_cases.json`.
- Keep old prompt output compatible.
- Remove unconditional `strip_needless_markers()` path that conflicted with
  LLM#2 fallback authority.

### Phase 2: Prompt Evaluation Set Execution ✅

Completed 2026-05-19.

Goal: make Prompt Evaluation Set V1 executable instead of relying on random
sampling.

Completed work:

- Store Prompt Evaluation Set V1 in a machine-readable artifact
  (`optimization_runs/requirement_sets/prompt_eval_v1.json`, 30 entries).
- Add `--requirement-set <path>` to `optimization.cli run`.
- Validate that all listed Requirement IDs exist in the source Excel.
- Validate no duplicate keys, valid expected_missing_categories.
- Save the set name, path, and entry count in `summary.json`.
- Enrich `generated_cases.json` entries with `evaluation_bucket`,
  `expected_missing_categories`, and `requirement_set_note`.
- Preserve original `--sample` / `--seed` behavior when `--requirement-set`
  is not given.
- Requirements are selected in set order when using `--requirement-set`.

### Phase 3: Hard-Gate Evaluation

Goal: align the automated evaluator and reports with the missing-information
quality policy.

Required work:

- Synchronize `CHECKLIST` and `evaluate_case()` with `checklist_v2.md`.
- Report missing-information hard-gate failures separately from ordinary
  checklist failures.
- Show expected vs actual missing categories in evaluation reports.

### Phase 4: Manual Review Score

Goal: capture the human review rubric as structured data.

Required work:

- Define a review input format for the four manual scores.
- Compute the weighted score.
- Apply hard gates before accepting any weighted score.
- Render Manual Review Scores in the report without mixing them into automated
  checklist pass rate.

## Acceptance Criteria

The full optimization workflow is acceptable when:

- Parser tests cover old and new missing-info formats.
- Pipeline output carries states and observations from LLM#1 into LLM#2.
- Prompts keep the two-call architecture: analyze-and-plan first, one-case
  generation second.
- Prompt Evaluation Set V1 can be run without random sampling.
- Prompt Evaluation Set reports severe missing-info failures
  explicitly.
- Manual Review Scores can be recorded and weighted separately from automated
  checklist pass rate.
- Prompt changes do not improve scores merely by reducing case count,
  overusing `[NEEDS REVIEW]`, or avoiding concrete expected results.

## Out of Scope

- Changing from HTML output to JSON.
- Replacing the two-step LLM architecture.
- Adding HIL bench command generation.
- Treating tool commands, HIL channels, or bench configuration as
  `[NEEDS REVIEW]` semantics.
