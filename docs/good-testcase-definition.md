---
name: good-testcase-definition
description: Minimal definition of a good BMS HIL draft test case
status: draft
created: 2026-05-21
---

# Good BMS HIL Draft Test Case Definition

This document defines the minimal standard for a good AI-generated BMS HIL
draft test case. It is intentionally shorter than
`optimization_runs/scoring_rubrics.md`.

Use this document as the shared baseline for prompt writing, human review, and
future evaluator hard gates. Use the 8-dimension scoring rubric for detailed
diagnosis after a case has passed the basic quality bar.

## Core Principle

Information honesty is more important than surface completeness.

A draft case may be incomplete when the requirement is incomplete. It must not
pretend missing requirement semantics are known.

Good draft cases preserve the selected requirement's natural-language intent and
mark missing engineering details with `[NEEDS REVIEW]` instead of inventing
signals, thresholds, timings, states, observations, DTCs, CAN fields, HIL
channels, tool commands, or bench configuration.

Supplementary context is not generation authority. It may help a human reviewer
resolve `[NEEDS REVIEW]`, but it must not create new generated test objectives,
actions, or expected results for the current requirement.

## Minimal Definition

A good case:

1. Verifies the current requirement, not a related or imagined BMS behavior.
2. Tests one clear behavior branch, condition, mode, or transition.
3. Uses only information supported by the selected requirement or explicitly
   accepted test basis.
4. Preserves natural-language behavior when concrete engineering details are
   missing.
5. Marks missing engineering details with `[NEEDS REVIEW]` in the relevant
   action or expected result.
6. Has executable action steps and judgeable expected results.
7. Keeps precondition and postcondition consistent across cases.

## Hard Fail

The following make a case unacceptable regardless of weighted score:

- It tests a different requirement or unrelated BMS behavior.
- It turns supplementary context or neighboring functions into new generated
  test objectives, actions, or expected results for the current requirement.
- It invents unsupported signal names, thresholds, timing values, states,
  observations, DTCs, CAN fields, HIL channels, tool commands, or platform
  capability.
- It needs missing signal, threshold, timing, state, or observation information
  but does not mark the relevant action or expected result with
  `[NEEDS REVIEW]`.
- It replaces requirement behavior with an empty marker such as
  `[NEEDS REVIEW]` alone.
- Its expected result cannot support a pass/fail decision, for example
  "system works correctly" or "behaves as expected".
- Its steps are so abstract or mixed that an engineer would need to rewrite the
  test flow before review.

## `[NEEDS REVIEW]` Policy

`[NEEDS REVIEW]` marks missing engineering detail. It is not a replacement for
requirement semantics.

Allowed semantic gap categories:

- `signal`: missing controllable or observable BMS signal/interface.
- `threshold`: missing threshold value, calibration, comparison value, or
  boundary detail.
- `timing`: missing debounce time, confirmation time, timeout, wait duration,
  or sampling-related timing.
- `state`: missing BMS mode, operating state, fault state, latch state, or
  recovery state.
- `observation`: missing observable evidence such as DTC, CAN signal, fault
  record, log, status, limit request, or report metric.

Do not use `[NEEDS REVIEW]` for missing HIL channel names, tool commands, bench
setup, or automation-framework details unless the requirement itself depends on
that semantic information.

When the requirement gives a natural-language concept but not an executable
value or observable object, keep the concept and append `[NEEDS REVIEW]`.

Good:

```text
Action: Set cell voltage above overvoltage threshold [NEEDS REVIEW]
Action: Wait debounce time [NEEDS REVIEW]
Expected: overvoltage fault is set [NEEDS REVIEW]
Expected: charging is prevented [NEEDS REVIEW]
```

Bad:

```text
Action: Set cell voltage to 4.2V
Action: Wait 500ms
Expected: BMS_CellOV_Flag == 1
```

The bad example is unacceptable if those concrete values or signal names were
not provided by the selected requirement or explicitly accepted test basis.

Also bad:

```text
Action: [NEEDS REVIEW]
Expected: system works correctly [NEEDS REVIEW]
```

This loses the requirement behavior and remains unjudgeable.

## Case-Level Standard

Each single case should be focused and structured:

- The objective, actions, and expected results all trace to the same
  requirement behavior.
- Actions are concrete operations, not explanations of intent.
- Set, wait, check, restore, and reset actions are separated when they are
  distinct operations.
- Wait steps should not hide verification logic.
- A Set step may verify only that the stimulus/input condition was established;
  BMS response expectations belong after a wait-for-response step.
- Expected results describe the required outcome, state, status, or behavior.
- If a concrete observable object is known, use it exactly as provided.
- If no concrete observable object is known, natural-language expected behavior
  plus `[NEEDS REVIEW]` is acceptable.
- Multiple synchronous outcomes from the same stimulus may appear in the same
  expected result.

Example:

```text
Action: Set BMS to charge mode
Action: Set cell voltage above overvoltage threshold [NEEDS REVIEW]
Action: Wait debounce time [NEEDS REVIEW]
Expected: overvoltage fault is set [NEEDS REVIEW] & current limit is active [NEEDS REVIEW]
```

The two outcomes do not need separate cases if they are caused by the same
stimulus and are expected at the same verification point.

## Case-Set Coverage Standard

Coverage is judged at the requirement level, across all generated cases for the
same requirement. More cases are not automatically better.

A good case set covers the independent behaviors required by the requirement:

- Positive trigger path: condition met, expected behavior occurs.
- Negative threshold path: condition below/not meeting threshold, behavior does
  not trigger.
- Negative timing path: condition present but duration is insufficient,
  behavior does not trigger.
- Different modes, branches, or operating states when they change behavior.
- Different threshold levels or fault levels when the requirement distinguishes
  them.
- Recovery, clear, latch, or state-transition direction when specified.

Do not create artificial exact-boundary cases when the requirement does not give
a concrete or symbolic threshold. When a threshold is known and the requirement
uses clear comparison language, preserve that boundary semantics. For example,
`at or above`, `at least`, and `reaches threshold` are inclusive; `above`,
`greater than`, and `exceeds` are strict.

Do not turn a calibration-parameter allowed range into generated endpoint cases
unless the selected requirement is actually about that range. If the selected
requirement itself defines a lower/upper behavior range, cover the range by its
inclusivity:

```text
[L, U]:  < L, >= L, midpoint, <= U, > U
(L, U): <= L, > L,  midpoint, < U,  >= U
[L, U): < L, >= L, midpoint, < U,  >= U
(L, U]: <= L, > L,  midpoint, <= U, > U
```

Use semantic relations with `[NEEDS REVIEW]` when concrete values are not part
of the selected requirement or explicitly accepted test basis.

Good:

```text
Action: Set cell voltage above overvoltage threshold [NEEDS REVIEW]
Action: Wait debounce time [NEEDS REVIEW]
Expected: overvoltage fault is set [NEEDS REVIEW]

Action: Set cell voltage below overvoltage threshold [NEEDS REVIEW]
Action: Wait debounce time [NEEDS REVIEW]
Expected: overvoltage fault is not set [NEEDS REVIEW]

Action: Set cell voltage above overvoltage threshold [NEEDS REVIEW]
Action: Wait shorter than debounce time [NEEDS REVIEW]
Expected: overvoltage fault is not set [NEEDS REVIEW]
```

The same policy applies to timing thresholds. Do not invent exact milliseconds
or epsilon-style boundary values unless they are provided by the test basis.

Separate debounce/confirmation timing from response-time bounds. Debounce,
confirmation, and hold times define when a condition has matured and can justify
both mature-trigger and immature-no-trigger cases. A response-time phrase such
as `within 50 ms` defines how quickly the system must respond after the trigger
condition is applied; it does not create a no-trigger case before 50 ms unless
the requirement also defines debounce or confirmation semantics.

## Precondition and Postcondition

Use consistent precondition and postcondition text across generated cases:

```text
Precondition: BMS initialized, all parameters within normal operating range, no active faults.
Postcondition: System returned to normal operating state.
```

Requirement-specific mode changes, fault injection, recovery, clear, reset, or
restore operations belong in the action steps, not in precondition or
postcondition.

Good:

```text
Action: Set BMS to charge mode
Action: Clear simulated overvoltage condition
Action: Reset fault latch
```

Avoid:

```text
Precondition: BMS is already in charge mode with an overvoltage fault active.
```

unless that text is only documenting a fixed external setup that is explicitly
provided by the test basis.

## Relationship to the 8-Dimension Rubric

This definition is the entry quality bar.

After a case satisfies the hard-fail rules above, use
`optimization_runs/scoring_rubrics.md` for detailed scoring:

- `requirement_alignment`: did the case test the right requirement?
- `information_integrity`: did it avoid unsupported facts and mark gaps?
- `executability`: can an engineer execute the steps?
- `observability`: does the expected result identify evidence to observe?
- `pass_fail_clarity`: can the observed evidence be judged objectively?
- `state_and_environment_control`: are state transitions and recovery controlled?
- `automation_readiness`: can the case be converted to structured automation?
- `coverage_value`: does the full case set provide meaningful requirement
  coverage?

Do not optimize prompts directly against all rubric detail at once. First make
generated cases pass this minimal definition and hard-fail policy. Then use the
8-dimension rubric to diagnose quality gaps.
