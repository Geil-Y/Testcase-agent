---
name: optimize-prompt-by-checklist
description: Iteratively improve LLM prompts through checklist-based evaluation. Use when optimizing prompts, running evaluation rounds, tuning generated BMS HIL test cases, or working with checklist/manual-review reports.
---

# Optimize Prompt by Checklist

Before running this skill, read the workflow source of truth:

`docs/optimization-workflow.md`

That document owns the current Prompt Evaluation Set size, checklist version,
CLI selection behavior, sanitization behavior, evaluator ownership, and report
generation flow. Do not duplicate or override those facts here.

## Modes

- **Eval-only mode**: generate and/or evaluate once; do not modify prompts.
- **Optimization mode**: generate, evaluate, diagnose, edit prompts, and repeat.

## Startup Questions

Ask only the questions needed for the selected mode:

1. Eval-only or optimization mode?
2. Which Excel file should be used?
3. Random exploration or fixed Prompt Evaluation Set?
4. Should Manual Review Scores be produced?
5. For optimization mode: checklist version and short goal name.

Use `docs/optimization-workflow.md` for the exact commands and selection
semantics.

## Eval-Only Rules

- Do not create a branch.
- Do not edit prompt files.
- Generate `evaluation_report.html`.
- Generate `cases_report.html` when the user needs to inspect cases.
- If Manual Review Scores are requested, write `manual_review_scores.json` and
  rerun `generate_report()`.

## Optimization Rules

- Preserve the LLM#1 -> LLM#2 flow.
- Preserve HTML output format.
- Modify prompt files only after reading the report and diagnosing concrete
  failures.
- Prefer fixing the lowest-quality cases from Manual Review Scores when
  available.
- If Manual Review Scores are not available, use automated checklist pass rate
  as the fallback signal.
- Keep each round focused; do not change more than a few prompt concerns in one
  round.

## Prompt Modification Rules

Use `REFERENCE.md` for prompt-editing constraints and evaluation guidance.
Keep prompt changes compact, non-contradictory, and aligned with the current
checklist.

## Implementation Map

Use `docs/optimization-workflow.md` as the authoritative implementation map.
If implementation ownership changes, update that file first and keep this skill
as a thin pointer.
