---
name: case-generation-philosophy
description: Non-optimizable philosophy for BMS HIL testcase generation
status: draft
created: 2026-05-23
---

# Case Generation Philosophy

This document defines the non-optimizable philosophy for prompt writing,
prompt debugging, and prompt review.

It is not a scoring rubric. It is the higher-level constraint that prevents
prompt optimization from learning to satisfy metrics while degrading generated
test case quality.

Any prompt patch, GEPA-style suggestion, evaluator recommendation, or manual
prompt edit must preserve this philosophy first and improve metrics second.

## Core Principle

A good BMS HIL/SIL draft test case is a requirements-traceable, repeatable
verification procedure that applies defined test conditions, stimulates one
requirement behavior or diagnostic distinction, and states objective expected
evidence for pass/fail judgment.

It is not:

- A restatement of the requirement.
- A checklist-shaped answer.
- A way to maximize coverage count.
- A defensive use of `[NEEDS REVIEW]` to avoid reasoning.
- A surface-complete case that invents missing engineering facts.

The generated case should help a HIL/SIL engineer verify and diagnose one
concrete requirement behavior to the boundary of known information.

## Non-Optimizable Principles

These principles are not adjustable by automated prompt optimization:

1. Traceability is mandatory: every case must verify the selected requirement,
   not neighboring context or imagined BMS behavior.
2. Information honesty is more important than surface completeness.
3. Repeatability is mandatory: the same test conditions should support the
   same pass/fail judgment across engineers and automation runs.
4. Expected results must name objective evidence or preserve
   requirement-level observable behavior when concrete evidence is missing.
5. Case count is not quality. More cases are justified only when they add
   different diagnostic value.
6. `[NEEDS REVIEW]` is a marker for missing requirement semantics, not a safe
   default.
7. Natural-language requirement behavior is usable test basis. Do not replace
   it with placeholders when it is enough for a draft case.
8. A draft case may contain marked unknowns, but every known step must be
   concrete, ordered, and reviewable; every unknown must be localized with
   `[NEEDS REVIEW]` at the exact missing semantic point.
9. Action and expected result are separate responsibilities: action changes
   the system; expected result judges evidence.
10. Prompt patches must protect test-case philosophy before optimizing pass
   rate, weighted score, or hard-gate counts.

## Case Splitting Philosophy

A new case is justified only when changing the condition changes the
requirement-relevant expected behavior, pass/fail judgment, or evidence needed
to prove it.

Split cases when the selected requirement defines:

- Different trigger branches that lead to different expected behavior.
- Different expected outcomes.
- Different operating modes, BMS states, fault states, or transition
  directions that change the expected behavior or acceptance criteria.
- Different observable evidence paths only when they correspond to different
  requirement-defined behaviors or acceptance criteria.
- A positive trigger path and selected requirement-critical negative
  conditions; do not enumerate all false-condition combinations.
- Debounce, confirmation, or hold-time maturity versus non-maturity.
- Debounce reset, intermittent-fault behavior, timer restart, or recovery
  before maturity when the selected requirement explicitly defines that timing
  behavior.
- Requirement-defined behavior ranges whose inclusivity affects the expected
  result.

Do not split cases merely because:

- More cases may improve a coverage-looking metric.
- The same behavior can be phrased in multiple ways.
- Multiple preconditions are listed but changing them does not change the
  requirement-relevant expected behavior.
- Multiple missing details appear in the same requirement.
- SIL and HIL are different execution platforms.
- Observation mechanisms differ but prove the same requirement behavior and
  acceptance criteria.
- Tool operations or bench setup differ but requirement behavior is the same.
- A calibration parameter has an allowed range unrelated to the selected
  requirement behavior.
- Recovery, reset, timeout, or diagnostic behavior exists in neighboring
  context but is not required by the selected requirement.
- Combinations of unsatisfied conditions can be enumerated without adding
  verification value.

Prefer a minimal set of high-value verification cases over a large set of
formally different but low-value cases.

## Missing Information Philosophy

`[NEEDS REVIEW]` means the selected requirement lacks semantic information
needed to avoid inventing test behavior.

Natural-language requirement behavior is valid test basis, but it is not
always complete executable evidence. Preserve the selected requirement wording
and append `[NEEDS REVIEW]` when concrete signal, threshold, timing, state, or
observation evidence is missing.

Use `[NEEDS REVIEW]` only for missing requirement semantics in these categories:

- `signal`
- `threshold`
- `timing`
- `state`
- `observation`

Use it when the missing detail affects:

- The stimulus or operation in an action.
- The expected result.
- The pass/fail judgment.
- The timing or state at which the expected result becomes valid.

Do not use `[NEEDS REVIEW]` for:

- Missing HIL channel names.
- Missing tool commands.
- Missing bench setup.
- Missing automation framework details.
- Missing calibration lookup values when a symbolic parameter is already given.
- Model uncertainty when the selected requirement gives enough draft-level
  semantics.

Do not replace usable requirement wording with a bare marker. Do not remove
`[NEEDS REVIEW]` merely because the natural-language behavior is understandable.

Do not use `[NEEDS REVIEW]` defensively. Over-marking is a quality failure
when it hides usable requirement meaning and teaches the model to avoid
engineering judgment.

## Information Integrity

The model must not invent:

- Signal names.
- Threshold values.
- Timing values.
- BMS states.
- DTCs.
- CAN IDs or fields.
- Fault records or memory locations.
- Observation points.
- Recovery, reset, latch, or timeout behavior.
- HIL commands, channels, or tool capabilities.

When the requirement provides a natural-language behavior without a concrete
engineering identifier, preserve that wording and mark the missing concrete
evidence.

Requirement wording:

```text
THEN charging shall be prohibited
```

Good when no concrete observable is provided:

```text
Expected: charging is prohibited [NEEDS REVIEW]
```

Bad:

```text
Expected: [NEEDS REVIEW]
```

Bad when not provided by the selected requirement or accepted test basis:

```text
Expected: <invented status signal> is inactive
```

Preserve requirement wording when concrete engineering names are missing. Do
not replace usable requirement semantics with generic placeholders.

## Action and Expected Boundary

Actions are test operations. Expected results are judgments over evidence.

Actions may:

- Apply or change a stimulus.
- Set or request a requirement-defined mode or event.
- Wait for timing, ordering, or system response.
- Restore an input when needed.
- Collect evidence when the collection operation itself is part of the test
  procedure.

Evidence-collection actions such as read, record, measure, capture, or monitor
are allowed only when they describe how evidence is collected. They must not
contain the pass/fail judgment.

Bad:

```text
Action: Verify charging is prohibited
Expected: null
```

Good:

```text
Action: Record charge permission status [NEEDS REVIEW]
Expected: charging is prohibited [NEEDS REVIEW]
```

Expected results should state:

- What object, behavior, state, status, or output is observed.
- What value, relation, direction, or condition is expected.
- When the expectation becomes valid.

A BMS response should not be expected in the same step that creates the
stimulus. Set the stimulus first, then wait or advance to the point where the
requirement response becomes valid.

## Executability Philosophy

A draft case may contain marked unknowns, but every known step must be
concrete, ordered, and reviewable; every unknown must be localized with
`[NEEDS REVIEW]` at the exact missing semantic point.

Allowed:

- Symbolic thresholds from the requirement.
- Requirement-derived relations such as above threshold, below threshold, or
  shorter than debounce time.
- Natural-language physical quantities or outcomes from the requirement, with
  `[NEEDS REVIEW]` when concrete control or observation evidence is missing.
- Evidence-collection actions that state how evidence is collected without
  embedding the pass/fail judgment.
- `[NEEDS REVIEW]` at the exact missing semantic point.

Not allowed:

- Empty actions such as "perform test".
- Empty expected results such as "works correctly".
- One step containing multiple independent operations.
- Unbounded waits that do not specify requirement-derived timing, event point,
  or `[NEEDS REVIEW]`.
- Hidden setup assumptions that are required for the behavior but not stated in
  precondition or steps.
- Pass/fail criteria that cannot be judged from the recorded evidence.
- Generic titles or objectives that add no test intent.
- Pseudo-specific signals, values, or observations that were not in the test
  basis.

The case should be reviewable by a HIL engineer without rewriting the test
flow from scratch.

## Coverage Value

Coverage value comes from verification complementarity, not volume.

Valuable coverage distinguishes:

- Trigger versus selected non-trigger behavior when the non-trigger case
  changes the expected result or acceptance criterion.
- Mature versus immature timing conditions when the requirement defines
  maturity.
- Requirement-defined state or mode differences.
- Requirement-defined fault levels, degradation levels, protection levels, or
  threshold levels.
- Distinct observable evidence only when the evidence corresponds to a separate
  requirement behavior or acceptance criterion.

Low-value coverage includes:

- Repeating the same expected behavior with slightly different wording.
- Enumerating arbitrary combinations of unsatisfied trigger conditions.
- Splitting synchronous outcomes that should be verified at the same point.
- Adding recovery, reset, timeout, or diagnostic cases not required by the
  selected requirement.
- Creating boundary cases from invented values or unrelated calibration ranges.
- Expanding the case set merely because an evaluator rewards more apparent
  coverage.

## Prompt Patch Rules

Prompt patches are allowed only when they preserve this philosophy.

Each patch candidate must state:

- The failure cluster it addresses.
- The evidence from generated cases or evaluations.
- The representative cases that should be manually reviewed.
- The prompt clause it changes.
- The philosophy principle it protects.
- The expected benefit.
- What quality may get worse if this patch is wrong.
- Whether a human accepted, rejected, or revised it.

A patch must be reviewed on representative generated cases, including:

- At least one case where the target failure occurs.
- At least one case where the patch could cause the opposite failure.

Do not accept a patch merely because it improves:

- Hard-rule pass rate.
- DeepSeek weighted score.
- Missing-category match count.
- Retry success rate.
- Case count moving closer to an expected number.

Metrics are diagnostic signals, not the definition of quality.

## Anti-Patterns

Reject prompt changes that encourage:

- Adding `[NEEDS REVIEW]` whenever uncertain.
- Removing `[NEEDS REVIEW]` merely because natural-language behavior is
  understandable.
- Generating more cases to look more complete.
- Treating every listed precondition as a separate negative test.
- Splitting by observation method when the requirement behavior and acceptance
  criterion are the same.
- Turning every checklist item into a visible case-writing rule.
- Using evaluator language as generated test-case language.
- Making prompts longer to paper over conflicting rules.
- Optimizing for the fixed evaluation set instead of the testcase philosophy.
- Encoding benchmark-specific answers into prompt rules.
- Replacing requirement wording with generic placeholders.
- Creating formally valid but low-value cases.
- Hiding low executability behind correct HTML structure.

## Relationship to Existing Quality Documents

Existing project documents are useful references, not unquestionable
authority.

`docs/good-testcase-definition.md` defines the current minimal acceptance bar.

`optimization_runs/scoring_rubrics.md` defines current detailed diagnostic
scoring.

If either document conflicts with this philosophy or with better test-case
judgment discovered during review, update the downstream document rather than
weakening this philosophy.

If a metric improvement conflicts with this philosophy, reject or revise the
prompt change.
