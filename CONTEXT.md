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

- **Review Comment** — human-supplied clarification attached to a Regenerate
  action, explaining why the LLM output was unsatisfactory and what the
  expected result is. Required (mandatory) for every Regenerate. Injected
  into the Regenerate prompt with explicit priority markers. Takes precedence
  over the original requirement text and the LLM's previous output.

- **Supplementary Info** — a catch-all field holding additional Excel column
  content beyond the core requirement fields. It is preserved for human review
  reference, but it is not generation authority for new test objectives,
  actions, expected results, identifiers, thresholds, or timing values.

- **Quality Checklist** — a set of 34 evaluation items across 6 categories
  derived from current project prompts and CodeX `case_generation` modules.
  Includes hard-gate items that make a case unacceptable and warning items that
  flag likely issues. Used by Claude Code (not the 7B model) to evaluate
  generated case quality. Items sourced from CodeX are annotated `[CodeX]`.
  Current version: `docs/quality/checklist_v2.md`.

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

- **Typed Test Basis** — the LLM-A output: structured JSON extracting
  allowed signals, thresholds, timing, states, observations, and identified
  missing information from the requirement text.

- **Case Intent Plan** — the LLM-B output: structured JSON listing the
  inferred case intents with coverage dimensions.

- **ABC Pipeline** — the three-stage linear generation pipeline
  (LLM-A test basis → LLM-B case intents → LLM-C HTML case writing).
  This is the sole legal generation pipeline as of 2026-05-29.
  Live at `src/testcase_agent/pipeline/generate.py`.

- **ABC Evaluator** — checklist v2 hard-rule evaluation run on ABC pipeline
  output. Lives at `src/testcase_agent/quality/evaluator.py` and is called by
  `src/testcase_agent/pipeline/evaluate.py` and the Pipeline Console.

## Pipeline Console

- **Pipeline Console** — a local web UI (React/Vite) for importing requirements,
  running the ABC pipeline with optional per-stage human review, and viewing
  generated test cases. Live at `console-ui/` (frontend) and
  `src/testcase_agent/console/` (FastAPI backend).

- **Console Database** — a SQLite file (`pipeline_console.db`) at the project
  root. Stores imported requirements, runs, LLM-A/B/C artifacts (test basis
  items, case intents, test cases with steps), review decisions, and evaluation
  results. Replaces the retired file-based artifact directory model.

- **Run** — one pipeline execution for a single Requirement. Has a status
  (`extraction_ready`, `intents_ready`, `cases_ready`, `evaluated`, `failed`)
  and a per-stage review configuration. A Requirement may have multiple Runs
  (1:N), preserving history.

- **Review Stage Configuration** — a per-Run setting (`review_required`) that
  specifies which LLM stages (a, b, c) require human review before advancing.
  Any subset may be set: none (full auto-approve), a only, b only, c only,
  a+b, a+c, b+c, or all three. Locked at Run creation time. Stages not in the
  set are auto-accepted: their LLM output is used as-is and the pipeline
  advances immediately.

- **Stage Advance** — the action of completing review on the current stage and
  triggering the next LLM stage. Requires the stage to be in Accepted state.
  When consecutive downstream stages are configured as auto-approve, the
  backend chains them in a single synchronous request. User-edited or
  regenerated test basis items override LLM-A's original output when advancing
  to LLM-B.

- **Accept** — a human review action that confirms the current stage's output
  as authoritative. Accept is a whole-stage decision (not per-item): clicking
  "Accept" locks all items in that stage and enables Stage Advance. Accept is
  reversible via Unlock. Accepted output becomes immutable downstream
  authority.

- **Regenerate** — a human review action that requests the LLM to re-produce
  output with a mandatory Review Comment explaining the deficiency. LLM-A
  supports per-item Regenerate (single test basis item re-extraction); LLM-B
  supports whole-plan Regenerate (entire intent plan re-planned, old versions
  preserved with a version number); LLM-C has no Regenerate. LLM-B Regenerate
  is capped at 3 attempts per Run; exceeding the limit forces the stage into
  Force Edit state.

- **Edit** — a human review action that directly modifies LLM output in-place
  without invoking the LLM. Available at all three stages. Edited content
  carries the same authority as Accepted content.

- **Force Edit** — a terminal review state entered when LLM-B Regenerate has
  been used 3 times without reaching Accept. In this state, Regenerate is
  disabled and the human must manually edit or delete intents to finalize the
  plan. Accept remains available.

- **Unlock** — an explicit action that reverses a stage-level Accept, returning
  all items in that stage to editable/regeneratable state. When Unlocking an
  upstream stage (e.g. LLM-A) while downstream data exists (LLM-B intents,
  LLM-C cases), a confirmation dialog warns that all downstream data will be
  cascaded as stale and must be regenerated.

## Retired Concepts

The clarification-first review pipeline (ADR-0003) has been retired and
superseded by the ABC pipeline. The following terms are historical:

- **Requirement Decomposition** — [RETIRED] the old LLM-A stage producing
  `clarification_review.json`.
- **Clarification Review** — [RETIRED] human review of requirement decomposition.
- **Clarified Test Basis** — [RETIRED] resolved understanding after clarification.
- **Case Intent Review** — [RETIRED] human review of proposed case intents.
- **Approved Case Plan** — [RETIRED] final case-writer-ready intents.
- **Review Workbench** — [RETIRED] interactive human review UI.
- **Confidence Routing** — [RETIRED] four-color confidence scoring system.
- **Pattern Tag** — [RETIRED] deterministic memory index for review decisions.

## Relationships

- A **Prompt Evaluation Set** contains multiple **Requirements**.
- A **Prompt Evaluation Set Entry** refers to exactly one **Requirement**.
- A **Requirement** can produce multiple **Test Cases** through the generation
  pipeline.
- A **Requirement** may have multiple **Runs** (1:N), preserving history of
  repeated pipeline executions.
- A **Run** belongs to exactly one **Requirement** and contains one set of
  LLM-A **TestBasis Sections and Items**, one set of LLM-B **Case Intents**,
  and one set of LLM-C **Test Cases** with **Steps**.
- User-edited **TestBasis Items** override LLM-A's original output and become
  the authority for downstream LLM-B and LLM-C stages.
- A **Test Case** is evaluated by the **Quality Checklist** and may also receive
  the case-level dimensions of a **Manual Review Score**.
- A **Hard Gate** can make a **Test Case** unacceptable even when other review
  scores are high.
- The **ABC Pipeline** is the sole legal generation path. It produces
  **Test Cases** from **Requirements** through the three-stage linear flow.
- The **Pipeline Console** reads and writes through the **Console Database**.

## Architecture principles

- **Code = plumbing.** The codebase provides the pipeline skeleton, provider
  abstraction, quality gate, and I/O. It owns no generation philosophy.
- **Prompt = soul.** Coverage heuristics, case-writing style, depth, and
  domain knowledge live entirely in standalone prompt files. Changing models
  or case philosophy means editing prompts, not code.
- **LLM does one thing at a time.** Each LLM call has a narrow, well-defined
  input and output. The 7B/8B model constraint means we keep each prompt as
  lean as possible.
