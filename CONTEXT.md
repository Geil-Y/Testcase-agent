# Testcase Agent — Domain Context

A testcase generation agent that uses newer LLM Provider models to produce BMS
HIL test cases from structured requirements.

## Glossary

- **Requirement** — a single BMS behavior specification imported from Excel.
  Must have a `requirement_key` and `description`. May carry `function_name`,
  `requirement_type` (requirement / heading / info), and `supplementary_info`
  (extra columns mapped at import time). In Prompt Learning, Requirements
  missing a requirement key or description are excluded from learning and
  recorded as data issues. Duplicate Requirement keys keep the first valid row;
  later duplicates are ignored and recorded as data issues.

- **Test Case** — a generated verification procedure composed of a title,
  objective, pre_condition, steps (each with action + expected_result), and
  post_condition. Belongs to exactly one requirement.

- **Reference Test Case** — a manually written and human-reviewed historical
  test case asset used as an exemplar for learning case-writing style,
  boundary-value selection, coverage habits, and review-approved quality
  expectations. It is not an LLM-generated output from the current Run.
  Reference Test Case Excel rows include separate action and expected-result
  columns; each cell may contain multiple steps with inconsistent separators.
  Prompt Learning preserves raw cell text as the primary learning input and may
  derive step splits only as auxiliary structure. Action and expected-result
  entries are not required to be one-to-one; one action may contain multiple
  operations, and expected results may contain multiple observations or omit a
  direct counterpart for some actions. Each Reference Test Case Excel row
  represents one Reference Test Case. Required mapped columns are case id,
  linked requirement identifiers, title, action, and expected result; objective
  is optional. If a row lacks a case id but has usable title/action/expected
  content and Requirement links, Prompt Learning may assign a temporary
  sheet-and-row identifier and record the missing case id as a data issue.
  If a row lacks a title but has usable action/expected content, it may still
  participate in learning and the missing title is recorded as a data issue.
  Rows missing either action or expected-result content are excluded from
  learning and recorded as data issues.
  Case ids are expected to uniquely identify Reference Test Cases across the
  selected case sheets; duplicate case ids are data issues but do not fail
  Prompt Learning, and duplicate rows may still participate in learning.
  If a row lacks linked Requirement identifiers but has usable case content,
  Prompt Learning may keep it as a style-only Reference Test Case example while
  recording the missing links as a data issue; it cannot contribute to
  Requirement-to-Reference-Test-Case coverage learning and should only inform
  LLM-C case-writing style.

- **No-Test Requirement** — a Requirement that has no linked Reference Test
  Case in the historical case Excel. Prompt Learning treats unlinked
  Requirements as likely no-test examples for learning no-test patterns, rather
  than requiring a separate human applicability label. Heading/info requirement
  rows may also be used as no-test learning examples when they have no linked
  Reference Test Case; explicit links take precedence over requirement type.

- **Prompt Learning** — an offline learning activity that uses Requirements and
  Reference Test Cases to produce candidate prompts for LLM-A, LLM-B, and
  LLM-C. Its goal is prompt
  generation, not test case generation. Prompt Learning defines a general
  learning framework and guardrails; it should not hard-code narrow prompt
  writing rules that prevent later strategy iteration. It uses the same LLM
  Provider abstraction as generation, but may use a separate model
  configuration from the model later used to run the ABC Pipeline. Its input is
  two Excel files rather than a separate corpus-management system: one
  Requirement Excel file where the user selects one Requirement sheet, and one
  Reference Test Case Excel file that may contain multiple sheets.
  The first version should stay intentionally simple; advanced management,
  validation, editing, export, cancellation, and cleanup features can be added
  later when real usage shows they are needed.

- **Learned Prompt Set** — the three candidate prompt pairs produced by Prompt
  Learning: `analyze_test_basis.system.html`,
  `analyze_test_basis.user.html`, `plan_case_intents.system.html`,
  `plan_case_intents.user.html`, `generate_case.system.html`, and
  `generate_case.user.html`. A Learned Prompt Set is a candidate artifact
  containing complete `.html` prompt text for human review and comparison; it
  does not automatically replace the active production prompts and does not
  need to include prompt diffs. It may include a concise learning rationale to
  help humans review why the candidate prompts were produced. Learned Prompt
  Sets are versioned as files so candidates can be reviewed, compared, and
  traced over time. Their metadata records a summary of learning inputs rather
  than embedding all historical asset content, including the LLM Provider/model
  used for Prompt Learning and parsed-input summary counts. Data issue metadata
  includes enough location detail, such as file type, sheet, row, issue type,
  and message, to help users locate source Excel problems.
  Learned prompt text is written in English; the learning rationale may be
  written in Chinese for reviewer convenience.
  Uploaded Requirement and Reference Test Case Excel files are temporary run
  inputs and are deleted after the run; official Learned Prompt Set folders do
  not embed the original historical asset files.
  Version folder names use a timestamp, with a short suffix when needed to avoid
  collisions.
  `rationale.md` is a concise review aid rather than a long report. It should
  summarize the mainstream learned style, coverage and boundary-value
  tendencies, no-test patterns, notable conflicts, and data issue summary.

- **Prompt Learning Framework** — the stable compatibility frame that learned
  prompts must satisfy, including the six output prompt files, expected template
  variables, required output formats, and ABC stage responsibilities. Prompt
  Learning may read the active production prompts as compatibility references,
  but historical assets are the source for learned style and coverage habits.
  The framework is fixed by code; the LLM fills prompt content inside that
  framework and does not decide file structure, template variables, or stage
  schemas. The framework follows the active ABC prompt variable names and
  output formats so a reviewed Learned Prompt Set can later replace same-named
  production prompt files without pipeline code changes. Learned prompts may
  change surrounding wording and structure, but must preserve required template
  variables and must not introduce variables the pipeline does not provide.
  Prompt Learning validates generated prompt files against this framework before
  saving a Learned Prompt Set as an official version.

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
  flag likely issues. Used by Claude Code or an evaluator separate from the
  generation provider to evaluate generated case quality. Items sourced from
  CodeX are annotated `[CodeX]`.
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

- **Prompt Learning Page** — a standalone page option alongside the existing
  Pipeline Console page. It provides the Prompt Learning UI workflow but does
  not reuse Run, Stage Advance, or ABC Pipeline execution state. The first
  version may store the most recent column mapping in browser localStorage
  rather than the Console Database. It can list versioned Learned Prompt Set
  folders from the file system for review. The first version does not provide
  an "activate prompt set" action or zip download; generated Learned Prompt
  Sets are automatically saved under `prompts/learned/<version>/`.
  Learned Prompt Set contents are displayed read-only in the first UI version.
  After a successful run, the UI defaults to showing `rationale.md` for the new
  Learned Prompt Set. Prompt files are grouped for display by LLM-A, LLM-B, and
  LLM-C, with system and user prompt text shown as read-only panels within each
  group.
  The page should show a concise parsed-input summary after learning runs, such
  as requirement count, reference case count, valid link count, unlinked
  requirement count, style-only case count, and data issue count. Data issue
  details may be shown in an expandable section.

- **Console Navigation** — the web app opens through one shared UI shell with a
  left-side selector containing at least two page options: Case Generation and
  Prompt Learning.
- Case Generation and Prompt Learning share the same application startup path
  and backend server; Prompt Learning is not a separate service.

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
- A **Requirement** may be linked to zero or more **Reference Test Cases**.
  Having zero linked Reference Test Cases may mean the Requirement does not
  need test coverage, not necessarily that historical coverage is missing.
- In **Prompt Learning**, Requirements with no linked Reference Test Case are
  treated as likely **No-Test Requirements** for learning no-test patterns.
- Multiple Reference Test Case rows linking to the same Requirement identifier
  are expected and represent the normal case where one Requirement has multiple
  Reference Test Cases; this is not a duplicate data issue.
- A **Reference Test Case** may be linked to one or more **Requirements**, but
  every Reference Test Case must be linked to at least one Requirement.
  Reference Test Case to Requirement links are provided by one column in the
  Reference Test Case Excel file; that column may contain multiple Requirement
  identifiers. Link parsing should tolerate common separators such as newline,
  comma, semicolon, and Chinese punctuation rather than depending on a single
  delimiter.
- When a **Reference Test Case** is linked to multiple **Requirements**, prompt
  learning treats each link as an independent Requirement-to-Reference-Test-Case
  example. The generated ABC Pipeline remains Requirement-centered: one
  Requirement may produce multiple generated Test Cases, but generated Test
  Cases do not need to cover multiple Requirements.
- Reference Test Case links that point to unknown Requirement identifiers are
  ignored for learning and recorded as data issues in metadata or rationale;
  they do not fail the Prompt Learning run. If all links on a Reference Test
  Case point to unknown Requirements, that Reference Test Case is excluded from
  learning and recorded as a data issue.
- **Prompt Learning** produces a **Learned Prompt Set**. It does not run the
  ABC Pipeline and does not itself generate Test Cases.
- Prompt Learning does not automatically smoke-test or evaluate generated
  prompts by running the ABC Pipeline; prompt effectiveness validation is a
  separate activity.
- In **Prompt Learning**, **Reference Test Cases** help infer review-approved
  style, coverage habits, boundary-value tendencies, and no-test patterns. The
  resulting prompts must keep new-generation authority grounded in the input
  Requirement and remain human-reviewable. Mixed Chinese/English historical
  content is preserved as source text rather than translated or normalized.
- **Prompt Learning** uses all available historical assets by default rather
  than requiring a manually curated learning set.
- If historical assets contain inconsistent styles, **Prompt Learning**
  produces one mainstream-style **Learned Prompt Set** and notes obvious
  conflicts in the learning rationale.
- Prompt Learning may use an internal multi-step learning process over the full
  historical asset set rather than sending all inputs in one large LLM request.
  The internal strategy can evolve as long as the user-visible output remains a
  single versioned Learned Prompt Set.
- Failed Prompt Learning attempts do not appear in the official Learned Prompt
  Set version list. The UI should show a clear error message identifying where
  the run failed, including framework validation failures when generated
  prompts are incompatible. Hard failures include unreadable Excel files,
  missing selected sheets, missing mapped columns, no valid Requirements, no
  learnable Reference Test Cases, LLM Provider failure, framework validation
  failure, and file save failure. Other source-data problems should generally
  be recorded as data issues while learning continues.
  The Learned Prompt Set version list shows a small set of metadata fields:
  version, creation time, requirement count, reference case count, data issue
  count, and model.
- Prompt Learning runs synchronously in the first version, with UI progress
  displayed across major stages. It does not need true percentage progress.
- Prompt Learning UI may accept an optional free-text learning instruction for
  the current run. The instruction can guide emphasis but cannot override the
  fixed Prompt Learning Framework. When provided, it is recorded in Learned
  Prompt Set metadata.
- The Reference Test Case Excel file may have multiple sheets, but Prompt
  Learning assumes those sheets share the same column structure.
- The Prompt Learning UI lets users choose which Reference Test Case sheets to
  include, with all sheets selected by default.
- Prompt Learning requires explicit manual column mapping for Requirement Excel
  and Reference Test Case Excel inputs; it does not infer mappings
  automatically.
- Prompt Learning is exposed first as a simple UI workflow for uploading the
  Requirement Excel and Reference Test Case Excel, configuring column mappings,
  running learning, and downloading or reviewing the resulting Learned Prompt
  Set. It remains independent from running the ABC Pipeline.
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
  input and output. Newer provider models reduce the old 7B/8B constraint, but
  prompts should still preserve clear stage boundaries and avoid unnecessary
  task mixing.
