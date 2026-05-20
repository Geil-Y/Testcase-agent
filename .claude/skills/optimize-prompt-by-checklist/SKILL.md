---
name: optimize-prompt-by-checklist
description: Iteratively improve LLM prompts through checklist-based evaluation. Use when optimizing prompts, running evaluation rounds, tuning generated BMS HIL test cases, or working with checklist/manual-review reports.
---

# Optimize Prompt by Checklist

This skill is the single source of truth for the prompt optimization workflow.
It owns the current artifacts list, CLI selection semantics, sanitization
behavior, evaluator ownership, startup questions, and per-mode workflows.

## Current Artifacts

| Artifact | Current source |
| --- | --- |
| Current checklist | `optimization_runs/checklist_v2.md` |
| Prompt Evaluation Set | `optimization_runs/requirement_sets/prompt_eval_v1.json` |
| Prompt Evaluation Set size | 35 entries |
| 8-dimension scoring rubric | `optimization_runs/scoring_rubrics.md` |
| Evaluation engine (hard-rule) | `optimization/evaluator.py` |
| AI evaluation engine (DeepSeek 8-dimension) | `optimization/claude_evaluator.py` |
| Case display renderer | `optimization/generate_case_html.py` |
| Evaluation report renderer | `optimization/generate_report.py` |
| Manual Review Score loader | `optimization/manual_review.py` |
| Round directory layout | `optimization_runs/log/<run-name>/round_<NN>/` |

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

5. **Checklist version:** Which checklist to evaluate against?
6. **Goal name:** Short name for this run (used in branch name and log directory).
7. **Max rounds:** How many rounds to run? Options: "3", "5", "10", or "Custom".

## CLI Selection Modes

### Random Exploration

Use `--sample` and optional `--seed` without `--requirement-set`.

```powershell
python -m optimization.cli run `
  --excel requirements.xlsx `
  --sample 20 `
  --seed 42 `
  --output-dir optimization_runs/log/<run-name>/round_01
```

### Fixed Prompt Evaluation Set

Use `--requirement-set` to run the Prompt Evaluation Set V1 in file order.
The set is self-contained — entries have inline `description`,
`function_name`, and `supplementary_info`, so `--excel` is NOT required.

```powershell
# Full 35-entry set
python -m optimization.cli run `
  --requirement-set optimization_runs/requirement_sets/prompt_eval_v1.json `
  --output-dir optimization_runs/log/<run-name>/round_01

# First N entries only
python -m optimization.cli run `
  --requirement-set optimization_runs/requirement_sets/prompt_eval_v1.json `
  --limit 5 `
  --output-dir optimization_runs/log/<run-name>/round_01
```

When `--requirement-set` is provided:
- `--sample` and `--seed` are ignored.
- `--limit N` runs only the first N entries.
- `--excel` is only needed as a fallback when set entries lack inline `description` (legacy sets).
- `generated_cases.json` is enriched with `evaluation_bucket`, `expected_missing_categories`, and `requirement_set_note`.
- `summary.json` records `requirement_set_name`, `requirement_set_path`, and `total_requirement_set_entries`.

## Sanitization

Sanitization is ON by default for `optimization.cli run`.

- Use `--no-sanitize` to disable it.
- Sanitization replaces invented numeric values with `[NEEDS REVIEW]`.
- Each case in `generated_cases.json` records case-level provenance: `sanitize.enabled`, `sanitize.replacement_count`, and `sanitize.replacements`.

## Evaluation Architecture

`optimization/evaluator.py` owns checklist and hard-gate logic:
- `CHECKLIST`
- `evaluate_case()`
- `evaluate_missing_info_hard_gates()`
- `evaluate_generated_cases()`

Renderers consume evaluator results:
- `optimization/generate_report.py` renders `evaluation_report.html` (checklist/hard-gate summary).
- `optimization/generate_case_html.py` renders `cases_report.html` (unified main report combining hard-rule, DeepSeek, and ChatGPT evaluations).

### DeepSeek AI Review

DeepSeek uses the 8-dimension scoring rubric in `optimization_runs/scoring_rubrics.md`.
It evaluates requirement groups, not isolated flattened cases:

- `coverage_value` is scored once per requirement over the full generated case set.
- Other 7 dimensions are scored per case.
- `deepseek_evaluation.json` stores both nested `requirements` and flattened `cases`.
- `overall_weighted` is computed by averaging per-requirement weighted scores.

### Manual Review Scores

If `<round_dir>/manual_review_scores.json` exists, `generate_report()` loads it,
applies evaluator-backed hard gates, and renders the Manual Review Scores section.

Format uses the same 8-dimension structure. See `optimization/manual_review.py`.

### Acceptance Signal Priority

1. Manual Review Scores (when available)
2. AI Review Scores (`deepseek_evaluation.json`, rendered in `cases_report.html`)
3. Automated checklist pass rate (hard-rule fallback)

## Eval-Only Workflow

1. Generate cases with either random exploration or the full Prompt Evaluation Set.
2. Run `generate_round_html()` to produce `cases_report.html`.
3. Optionally generate `evaluation_report.html`.
4. Optionally run AI evaluation: `python -m optimization.cli evaluate --round-dir <round_dir>`
5. Optionally write `manual_review_scores.json` and rerun `generate_round_html()`.

```powershell
python -c "from pathlib import Path; from optimization.generate_case_html import generate_round_html; generate_round_html(Path('<round_dir>'), 1)"
python -m optimization.cli evaluate --round-dir <round_dir>
```

Rules:
- Do not create a branch.
- Do not edit prompt files.

## Optimization Workflow

### Per-Round Steps

1. Generate cases with the full Prompt Evaluation Set (acceptance signal).
2. Generate `cases_report.html`.
3. Optionally generate `evaluation_report.html`.
4. Run AI evaluation: `python -m optimization.cli evaluate --round-dir <round_dir>`
5. If using Manual Review Scores, write `manual_review_scores.json` and rerun `generate_round_html()`.
6. Diagnose the lowest-quality cases before editing prompts.
7. Modify prompt files only; preserve the LLM#1 -> LLM#2 flow and HTML output format.
8. Repeat for the next round.

### Optimization Rules

- Modify prompt files only after reading the report and diagnosing concrete failures.
- Prefer fixing the lowest-quality cases from the top acceptance signal.
- Keep each round focused; do not change more than a few prompt concerns in one round.

### Git Workflow

- When optimization mode starts, immediately create a branch named `optimize/<goal-name>` from the current branch.
- After each round, commit prompt file changes with a message that includes:
  - Round number and goal name
  - Case pass rate (from hard-rule checklist)
  - Overall average score across all 8 dimensions
  - The single dimension with the lowest average score

  Example:
  ```
  optimize(round-2): improve observability and pass/fail clarity

  Pass rate: 82% | Avg score: 3.4 | Lowest dim: observability (2.6)

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  ```
- Do NOT commit generated reports, evaluation JSON files, or round directories. Only commit prompt file changes.

### Exit Criteria

After each round's evaluation completes, check whether both conditions are met:

1. **Hard-rule case pass rate >= 90%** — read from `generate_round_html()` return
   value (also printed as `X%` in the summary line of `cases_report.html`).
2. **Overall weighted score >= 3.0** — read `overall_weighted` from
   `<round_dir>/deepseek_evaluation.json`.

Both must pass. If met, stop immediately and report the final results. If not
met, continue to the next round until max rounds is reached.

At the end of each round, report:
- Current pass rate and weighted score
- Whether each exit condition is met or not
- Rounds remaining

## Prompt Modification Rules

Use `REFERENCE.md` for prompt-editing constraints and evaluation guidance. Keep prompt changes compact, non-contradictory, and aligned with the current checklist.

## Round Directory Layout

```
optimization_runs/log/<run-name>/
├── round_01/
│   ├── prompts/
│   ├── sampled_requirements.json
│   ├── summary.json
│   ├── generated_cases.json
│   ├── hardrule_evaluation.json
│   ├── deepseek_evaluation.json
│   ├── chatgpt_evaluation.json
│   ├── manual_review_scores.json   (optional)
│   ├── evaluation_report.html
│   └── cases_report.html
└── ...
```

Generated run logs under `optimization_runs/log/` are git-ignored.
