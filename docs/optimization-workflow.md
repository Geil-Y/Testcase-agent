# Optimization Workflow

**Status:** source of truth
**Last updated:** 2026-05-20

This document is the single source of truth for prompt optimization workflow
facts. Do not duplicate the current set size, checklist version, CLI selection
semantics, or evaluator ownership in skill docs or README files. Link here
instead.

## Current Artifacts

| Artifact | Current source |
| --- | --- |
| Current checklist | `optimization_runs/checklist_v2.md` |
| Prompt Evaluation Set | `optimization_runs/requirement_sets/prompt_eval_v1.json` |
| Prompt Evaluation Set size | 35 entries |
| Evaluation engine | `optimization/evaluator.py` |
| Case display renderer | `optimization/generate_case_html.py` |
| Evaluation report renderer | `optimization/generate_report.py` |
| Manual Review Score loader/summary | `optimization/manual_review.py` |

## CLI Selection Modes

The optimization CLI has two requirement selection modes.

### Random Exploration

Use `--sample` and optional `--seed` without `--requirement-set`.

```powershell
python -m optimization.cli run `
  --excel requirements.xlsx `
  --sample 20 `
  --seed 42 `
  --output-dir optimization_runs/log/<run-name>/round_01
```

This samples from all parsed requirement rows in the Excel file. It does not
attach Prompt Evaluation Set metadata such as `evaluation_bucket` or
`expected_missing_categories`.

### Fixed Prompt Evaluation Set

Use `--requirement-set` to run the full Prompt Evaluation Set V1 in file order.

```powershell
python -m optimization.cli run `
  --excel requirements.xlsx `
  --requirement-set optimization_runs/requirement_sets/prompt_eval_v1.json `
  --output-dir optimization_runs/log/<run-name>/round_01
```

When `--requirement-set` is provided:

- `--sample` and `--seed` are ignored.
- All keys in the set must exist in the Excel file.
- `generated_cases.json` is enriched with `evaluation_bucket`,
  `expected_missing_categories`, and `requirement_set_note`.
- `summary.json` records `requirement_set_name`, `requirement_set_path`, and
  `total_requirement_set_entries`.

There is currently no CLI support for random sub-sampling from the Prompt
Evaluation Set while preserving set metadata.

## Sanitization

Sanitization is ON by default for `optimization.cli run`.

- Use `--no-sanitize` to disable it.
- Sanitization replaces invented numeric values with `[NEEDS REVIEW]`.
- Each case in `generated_cases.json` records case-level provenance:
  `sanitize.enabled`, `sanitize.replacement_count`, and
  `sanitize.replacements`.

## Evaluation

`optimization/evaluator.py` owns checklist and hard-gate logic:

- `CHECKLIST`
- `evaluate_case()`
- `evaluate_missing_info_hard_gates()`
- `evaluate_generated_cases()`
- `evaluate_manual_review_hard_gates()`

Renderers consume evaluator results:

- `optimization/generate_report.py` renders `evaluation_report.html`.
- `optimization/generate_case_html.py` renders `cases_report.html`.

Manual Review Scores are optional. If `<round_dir>/manual_review_scores.json`
exists, `generate_report()` loads it, applies evaluator-backed hard gates, and
renders the Manual Review Scores section.

## Recommended Workflows

### Eval-Only Run

Use this for one-shot measurement without modifying prompts.

1. Generate cases with either random exploration or the full Prompt Evaluation
   Set.
2. Run `generate_report()` on the round directory.
3. Run `generate_round_html()` on the round directory if individual case
   browsing is needed.
4. Optionally write `manual_review_scores.json` and rerun `generate_report()`.

```powershell
python -c "from pathlib import Path; from optimization.generate_report import generate_report; generate_report(Path('<round_dir>'), 1, max_rounds=1)"
python -c "from pathlib import Path; from optimization.generate_case_html import generate_round_html; generate_round_html(Path('<round_dir>'), 1)"
```

### Optimization Run

Use this for prompt changes.

1. Choose checklist version and optimization goal for the run name.
2. Generate cases, normally with the full Prompt Evaluation Set for acceptance
   signal.
3. Generate `evaluation_report.html` and optionally `cases_report.html`.
4. If using Manual Review Scores, write `manual_review_scores.json` and rerun
   `generate_report()`.
5. Diagnose the lowest-quality cases before editing prompts.
6. Modify prompt files only; preserve the LLM#1 -> LLM#2 flow and HTML output
   format.
7. Repeat for the next round.

Acceptance is based on Manual Review Scores when available. Without Manual
Review Scores, use automated checklist pass rate as the fallback signal.

## Related Docs

- Prompt quality strategy and rubric: `docs/prompt-quality-optimization.md`
- Optimization run directory layout: `optimization_runs/README.md`
- Agent skill entry point: `.claude/skills/optimize-prompt-by-checklist/SKILL.md`
