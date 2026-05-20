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
| Evaluation engine (hard-rule) | `optimization/evaluator.py` |
| AI evaluation engine (DeepSeek 8-dimension scoring + checklist context) | `optimization/claude_evaluator.py` |
| Case display renderer | `optimization/generate_case_html.py` |
| Evaluation report renderer | `optimization/generate_report.py` |
| AI evaluation data (per evaluator) | `hardrule_evaluation.json`, `deepseek_evaluation.json`, `chatgpt_evaluation.json` |
| Manual Review Score loader/summary (8 dimensions) | `optimization/manual_review.py` |

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

- `optimization/generate_report.py` renders `evaluation_report.html` (checklist/hard-gate summary).
- `optimization/generate_case_html.py` renders `cases_report.html` (unified main report combining hard-rule, DeepSeek, and ChatGPT evaluations).

DeepSeek AI review uses the 8-dimension scoring rubric in
`optimization_runs/scoring_rubrics.md`. It evaluates requirement groups, not
isolated flattened cases:

- `coverage_value` is scored once per requirement over the full generated case
  set.
- `requirement_alignment`, `executability`, `observability`,
  `pass_fail_clarity`, `information_integrity`,
  `state_and_environment_control`, and `automation_readiness` are scored per
  case.
- `deepseek_evaluation.json` stores both nested `requirements` and flattened
  `cases` for report rendering. `overall_weighted` is computed by averaging
  per-requirement weighted scores.

Manual Review Scores are optional. If `<round_dir>/manual_review_scores.json`
exists, `generate_report()` loads it, applies evaluator-backed hard gates, and
renders the Manual Review Scores section.

`manual_review_scores.json` uses the same 8-dimension structure:

```json
{
  "requirements": [
    {
      "requirement_key": "REQ-001",
      "coverage_value": 4,
      "cases": [
        {
          "case_index": 0,
          "requirement_alignment": 5,
          "executability": 4,
          "observability": 4,
          "pass_fail_clarity": 3,
          "information_integrity": 5,
          "state_and_environment_control": 4,
          "automation_readiness": 4
        }
      ]
    }
  ]
}
```

## Recommended Workflows

### Eval-Only Run

Use this for one-shot measurement without modifying prompts.

1. Generate cases with either random exploration or the full Prompt Evaluation
   Set.
2. Run `generate_report()` on the round directory.
3. Run `generate_round_html()` on the round directory if individual case
   browsing is needed.
4. Optionally run AI evaluation (produces `deepseek_evaluation.json`, `chatgpt_evaluation.json`):
   `python -m optimization.cli evaluate --round-dir <round_dir>`
5. Optionally write `manual_review_scores.json` and rerun `generate_report()`.
6. `hardrule_evaluation.json` is auto-saved after hard-rule evaluation completes.

```powershell
python -c "from pathlib import Path; from optimization.generate_case_html import generate_round_html; generate_round_html(Path('<round_dir>'), 1)"
python -m optimization.cli evaluate --round-dir <round_dir>
```

### Optimization Run

Use this for prompt changes.

1. Choose checklist version and optimization goal for the run name.
2. Generate cases, normally with the full Prompt Evaluation Set for acceptance
   signal.
3. Generate `cases_report.html` (the unified main report). Optionally also generate `evaluation_report.html`.
4. Run AI evaluation to produce `deepseek_evaluation.json` and `chatgpt_evaluation.json`:
   `python -m optimization.cli evaluate --round-dir <round_dir>`
   `hardrule_evaluation.json` is auto-saved after hard-rule evaluation completes.
5. If using Manual Review Scores, write `manual_review_scores.json` and rerun
   `generate_report()`.
6. Diagnose the lowest-quality cases before editing prompts.
7. Modify prompt files only; preserve the LLM#1 -> LLM#2 flow and HTML output
   format.
8. Repeat for the next round.

Acceptance signal priority:
1. Manual Review Scores (when available)
2. AI Review Scores (`deepseek_evaluation.json`, `chatgpt_evaluation.json`, rendered in `cases_report.html`)
3. Automated checklist pass rate (hard-rule fallback)

## Related Docs

- Prompt quality strategy and rubric: `docs/prompt-quality-optimization.md`
- Optimization run directory layout: `optimization_runs/README.md`
- Agent skill entry point: `.claude/skills/optimize-prompt-by-checklist/SKILL.md`
