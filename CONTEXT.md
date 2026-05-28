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
  aims to verify, within its coverage dimension. In the current review
  pipeline, approved case intents are the direct input to LLM-C case writing.

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
  content beyond the core requirement fields. It is preserved for human review
  reference, but it is not generation authority for new test objectives,
  actions, expected results, identifiers, thresholds, or timing values.

- **Quality Checklist** — a set of 34 evaluation items across 6 categories
  derived from current project prompts and CodeX `case_generation` modules.
  Includes hard-gate items that make a case unacceptable and warning items that
  flag likely issues. Used by Claude Code (not the 7B model) to evaluate
  generated case quality. Items sourced from CodeX are annotated `[CodeX]`.
  Current version: `optimization_runs/checklist_v2.md`.

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

- **Requirement Decomposition** — LLM-A stage that breaks a requirement into
  facts, ambiguities, clarification questions, and a safe generation policy.
  Produces `clarification_review.json`.

- **Clarification Review** — human assessment of the LLM's requirement
  decomposition. Reviewer approves, clarifies, marks for review, blocks, or
  edits each ambiguity item. Validated before advancing.

- **Clarified Test Basis** — resolved requirement understanding after human
  clarification review. Contains approved facts and resolved ambiguities.
  Feeds the case intent planner.

- **Case Intent Review** — human assessment of proposed case intents.
  Reviewer approves, rejects, revises, merges, splits, or defers each intent.
  Validated to produce the approved case plan.

- **Review Workbench** — an interactive human review surface for review
  pipeline artifacts, initially covering Clarification Review and Case Intent
  Review while keeping JSON artifacts as the source of truth.

- **Pipeline Console** — a local full-flow UI for importing requirements,
  creating review runs, editing human review decisions, advancing validated
  pipeline stages, and viewing generated cases and evaluation results.

- **Active Run** — the single selected Requirement's current pipeline run in
  the Pipeline Console MVP.

- **Approved Case Plan** — final case-writer-ready intents. Only contains
  approved, revised, or split-child intents. Rejected, merged-away, and
  deferred intents are excluded.

- **Review Memory** — SQLite-based persistent storage of human review
  decisions with derived pattern tags. Advisory, not authoritative: may
  influence confidence and routing, but must not introduce behavior or
  intents not supported by the current requirement.

- **Confidence Routing** — four-color system (green/blue/orange/red) that
  maps LLM confidence scores to reviewer prioritization labels. Thresholds:
  green ≥ 0.85, blue ≥ 0.65, orange ≥ 0.40, red < 0.40.

- **Pattern Tag** — deterministic memory index derived by code from reason
  codes, ambiguity types, missing info categories, coverage dimensions, and
  conservative text detectors. Never generated by LLM, never edited by humans.
  Candidate tags (from text detectors) never act as authority.

## Relationships

- A **Prompt Evaluation Set** contains multiple **Requirements**.
- A **Prompt Evaluation Set Entry** refers to exactly one **Requirement**.
- A **Requirement** can produce multiple **Test Cases** through the generation
  pipeline.
- A **Test Case** is evaluated by the **Quality Checklist** and may also receive
  the case-level dimensions of a **Manual Review Score**.
- A **Hard Gate** can make a **Test Case** unacceptable even when other review
  scores are high.
- A **Pipeline Console** contains a **Review Workbench** for human review
  decisions.
- A **Pipeline Console** MVP advances exactly one **Active Run** at a time.

## Architecture principles

- **Code = plumbing.** The codebase provides the pipeline skeleton, provider
  abstraction, quality gate, and I/O. It owns no generation philosophy.
- **Prompt = soul.** Coverage heuristics, case-writing style, depth, and
  domain knowledge live entirely in standalone prompt files. Changing models
  or case philosophy means editing prompts, not code.
- **LLM does one thing at a time.** Each LLM call has a narrow, well-defined
  input and output. The 7B/8B model constraint means we keep each prompt as
  lean as possible.
