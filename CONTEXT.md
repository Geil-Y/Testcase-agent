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

- **Extracted Test Basis Sections** — the primary structured expression of
  requirement evidence extracted by LLM-A. They replace separate downstream
  facts and ambiguities, but they are not a case plan. Canonical sections
  are signals, thresholds, timing, states, and observations. Each item states
  whether it is `known` or `needs_review`. After clarification review, these
  sections become the approved evidence LLM-B uses to plan case intents and
  LLM-C uses to write executable cases.

- **Extracted Test Basis Section Item** — one entry inside an Extracted Test
  Basis Section. A `known` item carries explicit requirement-backed content. A
  `needs_review` item represents required test-basis information that the
  requirement description implies but does not explicitly provide, such as an
  unnamed signal, DTC, threshold, timing value, state, or observation point.
  Each item carries the extracted content when known, the missing need when
  unresolved, source text for review, and any human clarification that resolves
  the item. LLM-A actively identifies `needs_review` items only within the five
  canonical sections; it does not request HIL channels, tool commands, or bench
  configuration details.

- **Test Basis Section Review Decision** — a human decision attached directly
  to an Extracted Test Basis Section Item. Section items are the smallest
  reviewable unit in clarification review because they are the same units that
  later constrain LLM-B planning and LLM-C generation.

- **Prompt Test Basis View** — the compact, generation-facing rendering of
  reviewed Test Basis Sections. It separates usable known items from
  still-missing needs-review items and omits audit fields such as source,
  original status, and review decision so small local LLMs receive only the
  information needed for planning and case writing.

- **Resolved Section Item** — a Test Basis Section Item that originally needed
  review but was completed by a human clarification. Downstream planning and
  case writing treat the clarified content as known generation authority.

- **Unresolved Section Item** — a Test Basis Section Item that still needs
  review after clarification review. Downstream planning and case writing may
  continue when generation is otherwise safe, but must carry the unresolved
  semantic gap into the generated case as `[NEEDS REVIEW]`.
  LLM-B and LLM-C may only propagate unresolved items that already exist in the
  reviewed Extracted Test Basis Sections; they must not identify new missing
  information or add new `[NEEDS REVIEW]` markers on their own.

- **Blocking Test Basis Gap** — a missing or unclear requirement behavior that
  prevents a valid test skeleton from being planned, such as an unclear trigger,
  unclear expected behavior, mutually incompatible interpretations, or a
  non-testable heading/info row. Missing concrete test data such as a signal
  name, DTC code, threshold, timing parameter, state, or observation point is
  normally an Unresolved Section Item, not a Blocking Test Basis Gap.

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
  content beyond the core requirement description. It is preserved for human
  review reference, but it is not analysis or generation authority. Concrete
  identifiers, thresholds, timing, states, and observations must be grounded in
  the requirement description or explicitly supplied by human clarification.
  It is not passed to LLM-A, LLM-B, or LLM-C prompts; future review UI may show
  it to humans as reference only.

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

## Relationships

- A **Prompt Evaluation Set** contains multiple **Requirements**.
- A **Prompt Evaluation Set Entry** refers to exactly one **Requirement**.
- A **Requirement** can produce multiple **Test Cases** through the generation
  pipeline.
- LLM-A extracts **Extracted Test Basis Sections** from a **Requirement**.
- LLM-B plans **Case Intents** from the requirement description and reviewed
  **Extracted Test Basis Sections**. The description provides behavior
  semantics; reviewed sections provide concrete test materials.
- LLM-C writes **Test Cases** from approved **Case Intents** and reviewed
  **Extracted Test Basis Sections**. It may read the requirement description
  for behavior context, but concrete identifiers, parameters, states, timing,
  and observations must come from reviewed sections or human clarification.
  The case writer receives the current approved intent plus all reviewed
  sections, matching the legacy LLM2 pattern; intents do not need item-level
  basis references in the first implementation.
- The three-stage pipeline exists to split the legacy LLM1 responsibility:
  LLM-A extracts five concrete evidence sections and missing needs, while LLM-B
  plans coverage/case intents. LLM-C remains equivalent to the legacy LLM2 case
  writer pattern.
- Each LLM stage output is reviewable. LLM-A output review covers extracted
  sections and missing items. LLM-B output review covers planned case intents.
  LLM-C output review covers generated test cases through Accept, Edit, or
  Regenerate with a review comment.
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
