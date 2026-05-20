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

Ask these in order. Every question MUST use `AskUserQuestion` with options —
never open-ended text. Ask only the questions relevant to the path taken.

### Phase 1 — Mode & Source

1. **Mode:** Eval-only or optimization?
2. **Selection source:** Fixed Prompt Evaluation Set or random exploration?

### Phase 2 — Scope (depends on Phase 1 answer)

**If Fixed Prompt Evaluation Set:**
- How many requirements? Options: "All 35" or "First N" (specify N).
- The set is self-contained (inline descriptions). No Excel file needed.

**If random exploration:**
- Which Excel file?
- How many to sample?
- Random seed? (optional, for reproducibility)

### Phase 3 — Evaluation Signals

3. **AI Review Scores:** Produce DeepSeek 8-dimension scores? (Yes / No)
4. **Manual Review Scores:** Produce manual 8-dimension scores? (Yes / No)

### Phase 4 — Optimization Only

5. Which checklist version?
6. Short goal name for this run.

Use `docs/optimization-workflow.md` for the exact commands and selection
semantics.

## Eval-Only Rules

- Do not create a branch.
- Do not edit prompt files.
- Generate `cases_report.html` (the unified main report combining all evaluators).
- Optionally generate `evaluation_report.html` for checklist/hard-gate summary.
- If AI Review Scores are requested, run `python -m optimization.cli evaluate --round-dir <round_dir>`.
- If Manual Review Scores are requested, write `manual_review_scores.json` and
  rerun `generate_round_html()`.

## Optimization Rules

- Preserve the LLM#1 -> LLM#2 flow.
- Preserve HTML output format.
- Modify prompt files only after reading the report and diagnosing concrete
  failures.
- Prefer fixing the lowest-quality cases from Manual Review Scores when
  available.
- If Manual Review Scores are not available, prefer AI Review Scores
  (in `cases_report.html`) as the signal.
- If neither is available, use automated checklist pass rate as the fallback
  signal.
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
