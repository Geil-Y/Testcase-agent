---
name: optimize-prompt-by-checklist
description: Iteratively improve LLM prompts through checklist-based evaluation. Run the full optimization loop — generate cases, evaluate quality, diagnose failures, modify prompts, repeat. Use when the user wants to optimize prompts, improve generation quality, run optimization rounds, tune LLM output against a checklist, or mentions "checklist", "optimization loop", "prompt tuning", "evaluation report".
---

# Optimize Prompt by Checklist

Iteratively tune LLM prompts against a quality checklist. The core loop: generate → evaluate → diagnose → fix prompts → repeat.

## Startup: interactive configuration

Before any work begins, ask the user these 3 questions with `AskUserQuestion`. Use the defaults if the user doesn't override them:

| Question | Default |
|----------|---------|
| 最多运行几轮？ | 5 |
| Case 成功率到达多少后自动结束？ | 90% |
| 每轮随机采样多少条需求生成 case？ | 20 |

Once answered, store these as `MAX_ROUNDS`, `TARGET_PASS_RATE`, and `SAMPLE_SIZE` for the rest of the session. The stop condition in step 3 uses these values instead of hardcoded numbers.

## Git workflow

This is **mandatory** — every execution must follow these steps:

### 1. Create a dedicated branch

Ask the user for:
- Which checklist version this run targets (e.g. `v2`, `v3`)
- A short optimization goal in kebab-case (e.g. `tag-fix`, `sanitize`, `duplicate-detection`)

Branch naming convention:

```
optimize/<YYYYMMDD>_v<version>-<goal>
```

Examples: `optimize/20260519_v2-tag-fix`, `optimize/20260519_v2-sanitize`

Create the branch:

```
git checkout -b optimize/<YYYYMMDD>_v<version>-<goal>
```

If there are uncommitted changes on the current branch, warn the user and ask whether to stash or commit them first. Do not proceed until the working tree is clean on the new branch.

### 2. Commit after each round

After each round completes (generation + evaluation + prompt modification), commit using conventional commit format:

```
git add -A
git commit -m "$(cat <<'EOF'
perf(prompts): round N — case pass rate X% → Y%

<brief summary of what prompt changes were made and why>
EOF
)"
```

Commit type guidelines:
- `perf(prompts)` — default, improving pass rate / generation quality
- `fix(prompts)` — fixing a specific checklist item failure
- `refactor(prompts)` — restructuring prompts without changing behavior

Each commit captures the full state: modified prompts, generated cases, evaluation report, and archived prompt copies. This makes it easy to revert to any round's state or compare rounds with `git diff`.

## Output directory

All run artifacts go under `optimization_runs/log/<YYYYMMDD>_v<version>-<goal>/`. This directory is git-ignored (see `.gitignore`), so the log contents won't be committed — only the prompt changes and evaluation results tracked in the branch commits.

## Quick start

1. Ask the 3 configuration questions
2. Ask for a topic name, then create the git branch
3. Read the current checklist at `optimization_runs/checklist_v2.md`
4. Read the evaluation engine at `optimization/generate_case_html.py` (CHECKLIST dict + evaluate_case())
5. Run one round of generation + evaluation:
   ```
   python -m optimization.cli run --excel <file.xlsx> --sample <SAMPLE_SIZE> --output-dir optimization_runs/log/<YYYYMMDD>_v<version>-<goal>/round_01
   python -m optimization.generate_report  # adjust main() to point at the round dir
   ```
6. Read the generated `evaluation_report.html` in the round directory
7. Identify the top-failing checklist items and diagnose root cause
8. Modify prompt files under `prompts/` to address failures
9. Commit: `git commit -m "perf(prompts): round 1 — case pass rate X%"`
10. Repeat for next round with updated prompts

## The optimization round

Each round follows this exact sequence:

### 1. Sample & Generate
```
python -m optimization.cli run \
  --excel <path> \
  --sample <SAMPLE_SIZE> \
  --seed <n> \
  --output-dir optimization_runs/log/<YYYYMMDD>_v<version>-<goal>/round_0<N>
```
This samples requirements, saves current prompt files to `<round_dir>/prompts/` (automatic), runs the LLM#1→LLM#2 pipeline, and writes `generated_cases.json`.

### 2. Evaluate
Run the evaluation engine against the generated cases to produce `evaluation_report.html`:
```
python -c "
from pathlib import Path
from optimization.generate_report import generate_report
generate_report(Path('optimization_runs/log/<YYYYMMDD>_v<version>-<goal>/round_0<N>'), <N>, max_rounds=<MAX_ROUNDS>)
"
```
The report includes: overall case pass rate, per-category pass rates, per-item pass rates, worst-failing items, and failed case samples.

### 3. Decide: continue or stop?
- Pass rate ≥ `<TARGET_PASS_RATE>` → **stop** (target reached)
- Round `<MAX_ROUNDS>` reached → **stop** (max rounds)
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
git commit -m "$(cat <<'EOF'
perf(prompts): round N — case pass rate X% → Y%

<brief summary of prompt changes>
EOF
)"
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
| `optimization_runs/log/` | Run artifacts (git-ignored) |
| `optimization_runs/README.md` | Full protocol documentation |

## Checklist evolution

The checklist itself is iteratively improved. v1 (35 items) was created first. After 5 rounds of optimization, overlapping items were merged, misplaced items corrected, and the coverage methodology was rewritten — producing v2 (28 hard + 5 warning items). If the checklist needs revision, update `checklist_v2.md` and keep `CHECKLIST` dict in `generate_case_html.py` in sync.
