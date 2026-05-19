---
name: optimize-prompt-by-checklist
description: Iteratively improve LLM prompts through checklist-based evaluation. Run the full optimization loop — generate cases, evaluate quality, diagnose failures, modify prompts, repeat. Use when the user wants to optimize prompts, improve generation quality, run optimization rounds, tune LLM output against a checklist, or mentions "checklist", "optimization loop", "prompt tuning", "evaluation report".
---

# Optimize Prompt by Checklist

Iteratively tune LLM prompts against a quality checklist. The core loop: generate → evaluate → diagnose → fix prompts → repeat, targeting 90% case-level pass rate across max 5 rounds.

## Git workflow

Before starting optimization, create a dedicated branch:
```
git checkout -b optimize/run_<YYYYMMDD>
```
This isolates the optimization work from the main branch.

After each round completes (generation + evaluation + prompt modification), commit:
```
git add -A
git commit -m "optimize: round N — pass rate X% → Y%"
```
Each commit captures the full state: modified prompts, generated cases, evaluation report, and archived prompt copies. This makes it easy to revert to any round's state or compare rounds with `git diff`.

## Quick start

Start from an existing checklist and working prompts:

1. Read the current checklist at `optimization_runs/checklist_v2.md`
2. Read the evaluation engine at `optimization/generate_case_html.py` (CHECKLIST dict + evaluate_case())
3. Create a branch: `git checkout -b optimize/run_<YYYYMMDD>`
4. Run one round of generation + evaluation:
   ```
   python -m optimization.cli run --excel <file.xlsx> --sample 20 --output-dir optimization_runs/run_<ts>/round_01
   python -m optimization.generate_report  # adjust main() to point at the run dir
   ```
5. Read the generated `evaluation_report.html` in the round directory
6. Identify the top-failing checklist items and diagnose root cause
7. Modify prompt files under `prompts/` to address failures
8. Commit: `git commit -m "optimize: round 1 — pass rate X%"`
9. Repeat for next round with updated prompts

## The optimization round

Each round follows this exact sequence:

### 1. Sample & Generate
```
python -m optimization.cli run \
  --excel <path> \
  --sample 20 \
  --seed <n> \
  --output-dir optimization_runs/<run_id>/round_0<N>
```
This samples 20 requirements, saves current prompt files to `<round_dir>/prompts/` (automatic), runs the LLM#1→LLM#2 pipeline, and writes `generated_cases.json`.

### 2. Evaluate
Run the evaluation engine against the generated cases to produce `evaluation_report.html`:
```
python -c "
from pathlib import Path
from optimization.generate_report import generate_report
generate_report(Path('optimization_runs/<run_id>/round_0<N>'), <N>, max_rounds=5)
"
```
The report includes: overall case pass rate, per-category pass rates, per-item pass rates, worst-failing items, and failed case samples.

### 3. Decide: continue or stop?
- Pass rate ≥ 90% → **stop** (target reached)
- Round 5 reached → **stop** (max rounds)
- Otherwise → **continue** to step 4

### 4. Diagnose & modify prompts

Use the `/diagnose` skill for systematic root-cause analysis before touching any prompt file:

1. **Reproduce** — Identify the top-failing checklist items from `evaluation_report.html` (worst pass rates, highest failure counts)
2. **Minimise** — Pick the single worst item. Open `generated_cases.json` and find 2-3 cases that failed only on that item, not on many others
3. **Hypothesise** — For each failing case, read the case content against the checklist item definition. Ask: did the LLM ignore a rule, misunderstand it, or was the input missing critical info?
4. **Instrument** — Check the corresponding prompt file: is the rule present? Is it clear? Is it buried mid-prompt where a 7B model's attention decays?
5. **Fix** — Modify the prompt to address the root cause. Follow the modification rules in [REFERENCE.md](REFERENCE.md)
6. **Regression-test** — Before committing, review a few passing cases to ensure the prompt change doesn't break what already worked

Repeat for the next worst item, but never fix more than 3 items per round — the signal-to-noise ratio degrades when too many variables change at once.

### 5. Commit & next round
```
git add -A
git commit -m "optimize: round N — pass rate X%"
```
Then go back to step 1 with the updated prompts.

## Key files

| File | Role |
|------|------|
| `optimization/cli.py` | Batch generation CLI (sample + pipeline) |
| `optimization/generate_case_html.py` | Checklist evaluation engine + case display report |
| `optimization/generate_report.py` | HTML evaluation report generator (Chinese) |
| `optimization_runs/checklist_v2.md` | Current checklist (33 items, 6 categories) |
| `prompts/*.system.html` | Prompt templates to optimize |
| `optimization_runs/README.md` | Full protocol documentation |

## Checklist evolution

The checklist itself is iteratively improved. v1 (35 items) was created first. After 5 rounds of optimization, overlapping items were merged, misplaced items corrected, and the coverage methodology was rewritten — producing v2 (28 hard + 5 warning items). If the checklist needs revision, update `checklist_v2.md` and keep `CHECKLIST` dict in `generate_case_html.py` in sync.
