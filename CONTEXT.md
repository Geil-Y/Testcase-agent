# Testcase Agent — Domain Context

A testcase generation agent that uses a local LLM to produce BMS HIL test cases
from structured requirements.

## Glossary

- **Requirement** — a single BMS behavior specification imported from Excel.
  Must have a `requirement_key` and `description`. May carry `function_name`,
  `requirement_type` (requirement / heading / info), and `supplementary_info`
  (extra columns mapped at import time).

- **Test Case** — a generated verification procedure composed of a title,
  objective, pre_condition, steps (each with action + expected_result), and
  post_condition. Belongs to exactly one requirement.

- **Coverage Dimension** — the aspect of the requirement under test. Canonical
  values: `normal_behavior`, `boundary_or_threshold`, `fault_or_protection`,
  `state_transition`, `observability`.

- **BMS State** — a named operating, fault, latch, request, or recovery state
  that a generated test case may need to set, transition to, or verify.

- **Observation Point** — a requirement-level output that makes BMS behavior
  judgeable in a test case, such as a signal, flag, DTC, warning, limit request,
  or logged value.

- **Case Intent** — a one-sentence description of what a specific test case
  aims to verify, within its coverage dimension. Used as the per-case prompt
  input to LLM#2.

- **`[NEEDS REVIEW]`** — a marker inserted into test case content when the
  requirement semantics lack signal names, thresholds, timing, states, or
  observation points needed to avoid inventing test behavior; it does not cover
  HIL channel names, tool commands, or bench configuration details.

- **Missing Information Detection** — the ability to identify requirement
  semantic gaps that would otherwise force the model to invent test values or
  behavior.

- **Information Integrity** — the broader review dimension that checks whether
  concrete values, signals, timings, states, observations, diagnostics, bus
  messages, HIL channels, and tool commands are supported by the requirement or
  test basis, or honestly marked as `[NEEDS REVIEW]` when missing.

- **Missing Information Category** — one of the canonical semantic gap types:
  signal, threshold, timing, state, or observation.

- **Review Marker Text** — the literal marker shown in generated cases for all
  missing information categories; currently always `[NEEDS REVIEW]`.

- **Missing Information Detection Failure** — a critical quality failure where
  a test case should require `[NEEDS REVIEW]` but instead invents or assumes
  missing requirement information.

- **Missing Information Fallback** — a secondary safeguard where case writing
  marks requirement semantic gaps that were missed during earlier analysis.

- **Review Comment** — human-supplied clarification attached to a
  reject/regenerate action. Takes priority over the original requirement text
  when regenerating the case.

- **Supplementary Info** — a catch-all field holding additional Excel column
  content (signal names, thresholds, timing, etc.) beyond the core requirement
  fields. Used alongside `description` as input to LLM#1.

- **Quality Checklist** — a set of 33 evaluation items (6 categories, 28 hard + 5
  warning) derived from current project prompts and CodeX `case_generation`
  modules. Used by Claude Code (not the 7B model) to evaluate generated case
  quality. Items sourced from CodeX are annotated `[CodeX]`. Current version:
  `optimization_runs/checklist_v2.md`.

- **Prompt Evaluation Set** — a stable representative set of source
  requirements used to compare prompt changes with the same inputs and review
  criteria. It is not a set of generated test cases or reference answers.

- **Prompt Evaluation Set Entry** — one requirement's membership in a Prompt
  Evaluation Set, including why that requirement is useful for evaluating
  prompt quality and which missing information categories it is expected to
  exercise.

- **Evaluation Bucket** — a named reason for including a requirement in a
  Prompt Evaluation Set, such as complete-information baseline, threshold and
  timing boundary, missing-information trap, multi-branch behavior, or
  state/observation/diagnostic behavior.

- **Manual Review Score** — a human-assigned 8-dimension quality score for
  generated test cases. Coverage value is assigned at the requirement case-set
  level; requirement alignment, executability, observability, pass/fail
  clarity, information integrity, state/environment control, and automation
  readiness are assigned at the case level.

- **Hard Gate** — a quality rule that makes a generated test case unacceptable
  regardless of its other scores.

- **Optimization Run** — a timestamped execution of the prompt tuning loop.
  Contains multiple rounds. Each round saves its prompts, sampled requirements,
  generated cases, and an evaluation report.

- **Optimization Round** — one iteration within a run. Samples 20 requirements,
  generates cases with the current prompts, evaluates against the checklist
  (90% pass target), then modifies prompts based on failures. Maximum 5 rounds
  per run.

- **Evaluation Report** — Chinese HTML report produced each round by Claude Code.
  Contains per-category and per-item pass rates, failed case details, prompt
  diffs, and recommendations for the next round.

## Relationships

- A **Prompt Evaluation Set** contains multiple **Requirements**.
- A **Prompt Evaluation Set Entry** refers to exactly one **Requirement**.
- A **Requirement** can produce multiple **Test Cases** through the generation
  pipeline.
- A **Test Case** is evaluated by the **Quality Checklist** and may also receive
  the case-level dimensions of a **Manual Review Score**.
- A **Hard Gate** can make a **Test Case** unacceptable even when other review
  scores are high.

## Architecture principles

- **Code = plumbing.** The codebase provides the pipeline skeleton, provider
  abstraction, quality gate, and I/O. It owns no generation philosophy.
- **Prompt = soul.** Coverage heuristics, case-writing style, depth, and
  domain knowledge live entirely in standalone prompt files. Changing models
  or case philosophy means editing prompts, not code.
- **LLM does one thing at a time.** Each LLM call has a narrow, well-defined
  input and output. The 7B/8B model constraint means we keep each prompt as
  lean as possible.
