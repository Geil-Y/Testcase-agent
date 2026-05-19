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

- **Case Intent** — a one-sentence description of what a specific test case
  aims to verify, within its coverage dimension. Used as the per-case prompt
  input to LLM#2.

- **`[NEEDS REVIEW]`** — a marker inserted into test case content when the
  requirement text lacks concrete values (signal names, thresholds, timing).
  Signals to the human reviewer that the case needs supplemental information.

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

## Architecture principles

- **Code = plumbing.** The codebase provides the pipeline skeleton, provider
  abstraction, quality gate, and I/O. It owns no generation philosophy.
- **Prompt = soul.** Coverage heuristics, case-writing style, depth, and
  domain knowledge live entirely in standalone prompt files. Changing models
  or case philosophy means editing prompts, not code.
- **LLM does one thing at a time.** Each LLM call has a narrow, well-defined
  input and output. The 7B/8B model constraint means we keep each prompt as
  lean as possible.
