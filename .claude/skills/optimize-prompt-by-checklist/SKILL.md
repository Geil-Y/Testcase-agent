---
name: optimize-prompt-by-checklist
description: Iteratively improve LLM prompts through checklist-based evaluation. Run the full optimization loop — generate cases, evaluate quality, diagnose failures, modify prompts, repeat. Also supports eval-only mode for one-shot evaluation without prompt changes. Use when the user wants to optimize prompts, improve generation quality, run optimization rounds, tune LLM output against a checklist, or mentions "checklist", "optimization loop", "prompt tuning", "evaluation report".
---

# Optimize Prompt by Checklist

Iteratively tune LLM prompts against a quality checklist. Two work modes:

- **Optimization mode** — full loop: generate → evaluate → diagnose → fix prompts → repeat.
- **Eval-only mode** — generate and/or evaluate once, no prompt changes, no git branch, no commits.

## Startup: interactive configuration

Before any work begins, ask the user these 4 questions with `AskUserQuestion`. Use the defaults if the user doesn't override them:

| Question | Default | Options |
|----------|---------|---------|
| 是否为仅评估模式？ | 否（优化模式） | 优化模式 / 仅评估模式 |
| 最多运行几轮？ | 5 | 3 / 5 / 7（仅评估模式固定为 1） |
| 每轮从 Prompt Evaluation Set 随机采样多少条？ | 10 | 10 / 20 / 30 |
| 是否运行 Claude Code 自动评分（Manual Review）？ | 是 | 是 / 否 |

The auto-score question applies to both optimization and eval-only modes.

The source pool is the 30-entry Prompt Evaluation Set (defined in `optimization_runs/requirement_sets/prompt_eval_v1.json`). Each round randomly samples from these 30 entries — sampling is always random, not sequential.

### Eval-only mode — follow-up questions

When the user selects eval-only mode, ask 2 additional questions:

| Question | Default |
|----------|---------|
| 数据来源？ | 生成新的（使用当前 prompts + LLM） |
| 是否开启 `--sanitize`？ | 是 |

If the user chooses **使用已有 JSON**, ask for the path to `generated_cases.json`.  Skip generation entirely — go straight to evaluation.

For data source, the options are:
- **生成新的** — run `cli.py run` with the specified seed + sample size
- **使用已有 JSON** — provide path to an existing `generated_cases.json`

## Eval-only mode

When eval-only mode is active, the following rules apply:

- **No git branch** — work on the current branch, no branching or committing
- **No prompt modification** — skip diagnosis and prompt editing entirely
- **Single round only** — `MAX_ROUNDS` is forced to 1
- **Output directory** — use `optimization_runs/log/<YYYYMMDD>_v<version>-<goal>_evalonly/`
- **Generate case display HTML** — run `generate_round_html()` in addition to `generate_report()` so the user can browse individual cases
- **Report annotation** — note in the output that this is an eval-only run (not an optimization round)

### Eval-only flow

#### If generating new cases

```
python -m optimization.cli run \
  --excel <path> \
  --sample <SAMPLE_SIZE> \
  --seed <n> \
  [--no-sanitize] \
  --output-dir optimization_runs/log/<YYYYMMDD>_v<version>-<goal>_evalonly/
```

Then run evaluation (step 2 below).

#### If using existing JSON

Skip generation. Copy or symlink the JSON into the output directory, then run evaluation directly:

```python
# Produce evaluation_report.html
from pathlib import Path
from optimization.generate_report import generate_report
generate_report(Path('<output_dir>'), 1, max_rounds=1)

# Produce cases_report.html (case display)
from optimization.generate_case_html import generate_round_html
generate_round_html(Path('<output_dir>'), 1)
```

## Auto-Scoring (Claude Code as LLM-as-Judge)

When the user opts into auto-scoring, Claude Code acts as a stronger evaluator to produce `manual_review_scores.json`. This is a separate quality signal from the automated checklist evaluation — the two are rendered side-by-side in `evaluation_report.html`.

### Scoring protocol

Claude Code reads `generated_cases.json` **requirement by requirement**, scoring each case on four dimensions (1-5):

| Dimension | Weight | Question |
|-----------|--------|----------|
| Executability | 20% | Can a HIL engineer execute this procedure without rewriting? |
| Observability | 20% | Are expected results concrete and judgeable from BMS outputs? |
| Coverage Value | 20% | Does the case verify a meaningful requirement behavior or risk? |
| Missing Information Detection | 40% | Does the case identify requirement semantic gaps ([NEEDS REVIEW]) instead of inventing values? |

### Scoring rules for the agent

- Read the requirement description **first**, then the generated case.
- Compare what the case uses (signals, thresholds, timing, states, observation points) against what the requirement actually provides.
- If the case invents a value the requirement didn't give → penalize Missing Information Detection.
- If the case correctly places `[NEEDS REVIEW]` where semantics are missing → reward Missing Information Detection.
- If the requirement is semantically complete but the case adds unnecessary `[NEEDS REVIEW]` → minor penalty, but not automatic severe.
- `[NEEDS REVIEW]` only covers: signal, threshold, timing, state, observation. Ignore HIL channels, tool commands, bench config.
- Give brief `notes` explaining each dimension score, especially when scoring ≤2 or ≥4.

### Output

After scoring all cases, write `manual_review_scores.json` to the round directory. Format:

```json
[
  {
    "requirement_key": "REQ-BMS-OVP-001",
    "case_index": 0,
    "executability": 4,
    "observability": 3,
    "coverage_value": 5,
    "missing_information_detection": 2,
    "reviewer": "Claude Opus 4.7",
    "notes": "timing gap correctly flagged, but action order ambiguous"
  }
]
```

`case_index` is 0-based, matching the case's position in `generated_cases.json` for that requirement.

### Integration with report

After the JSON is written, re-run `generate_report()` — it automatically detects `manual_review_scores.json` and renders the Manual Review Scores section alongside the automated checklist pass rate. No code changes needed.

Relevant implementation: `optimization/manual_review.py`.

## Git workflow (optimization mode only)

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

| Mode | Path |
|------|------|
| Optimization | `optimization_runs/log/<YYYYMMDD>_v<version>-<goal>/` |
| Eval-only | `optimization_runs/log/<YYYYMMDD>_v<version>-<goal>_evalonly/` |

These directories are git-ignored (see `.gitignore`), so log contents won't be committed — only prompt changes and evaluation results tracked in the branch commits (optimization mode).

## Quick start

### Optimization mode

1. Ask the 4 startup questions
2. Ask for checklist version + goal, then create the git branch
3. Read the current checklist at `optimization_runs/checklist_v2.md`
4. Read the evaluation engine at `optimization/generate_case_html.py` (CHECKLIST dict + evaluate_case())
5. Run one round of generation + evaluation + (optional) auto-scoring:
   ```
   python -m optimization.cli run --excel <file.xlsx> --sample <SAMPLE_SIZE> --seed <n> --requirement-set optimization_runs/requirement_sets/prompt_eval_v1.json --output-dir optimization_runs/log/<YYYYMMDD>_v<version>-<goal>/round_01
   ```
   Then run evaluation and optionally auto-score:
   ```python
   from pathlib import Path; from optimization.generate_report import generate_report
   generate_report(Path('<round_dir>'), 1)
   ```
   If auto-scoring: score cases → write `manual_review_scores.json` → re-run `generate_report()`.
6. Read the generated `evaluation_report.html` in the round directory (checklist + hard gates + manual review)
7. Identify the lowest-scoring cases from Manual Review Scores and diagnose root cause
8. Modify prompt files under `prompts/` to address failures
9. Commit: `git commit -m "perf(prompts): round 1 — weighted score >3: X%"`
10. Repeat for next round with updated prompts

### Eval-only mode

1. Ask the 5 startup questions → select eval-only
2. Ask the 2 follow-up questions (data source + sanitize)
3. If generating new → run `cli.py run`; if using existing JSON → skip
4. Run `generate_report()` and `generate_round_html()` on the output directory
5. If auto-scoring enabled → score cases and write `manual_review_scores.json`, then re-run `generate_report()`
6. Report the pass rate, item breakdown, and manual review scores (if any) to the user — done

## The optimization round

Each round follows this exact sequence:

### 1. Sample & Generate

Sample SAMPLE_SIZE requirements randomly from the Prompt Evaluation Set, then generate:

```
python -m optimization.cli run \
  --excel <path> \
  --sample <SAMPLE_SIZE> \
  --seed <n> \
  --requirement-set optimization_runs/requirement_sets/prompt_eval_v1.json \
  --output-dir optimization_runs/log/<YYYYMMDD>_v<version>-<goal>/round_0<N>
```

The `--sample` and `--seed` are used for random sub-sampling from the 30-entry Prompt Evaluation Set. The CLI saves current prompt files to `<round_dir>/prompts/` (automatic), runs the LLM#1→LLM#2 pipeline, and writes `generated_cases.json`.

Note: For this to work, the CLI needs a `--sample` sub-sample from `--requirement-set`. Currently the CLI treats `--requirement-set` and `--sample` as mutually exclusive. If you encounter this, explain to the user that the CLI needs a small patch to support sub-sampling from a set — or run with `--sample N --seed <n>` without `--requirement-set` (random from full Excel) and flag it as a known gap.

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

Decision is based on **Manual Review Scores** (not automated checklist pass rate). If auto-scoring is enabled:

- **Score > 3 threshold**: Count cases where `weighted_score > 3.0`. If the count ≥ 90% of all scored cases → **stop** (target reached)
- **Round `<MAX_ROUNDS>` reached** → **stop** (max rounds)
- Otherwise → **continue** to step 4

If auto-scoring is not enabled, use the automated checklist pass rate instead: pass rate ≥ 90% → stop.

### 4. Diagnose & modify prompts

Use the `/diagnose` skill for systematic root-cause analysis before touching any prompt file.

Focus on **low-score cases from Manual Review** (when available), not random failures:

1. **Reproduce** — Open `manual_review_scores.json`. Sort by `weighted_score` ascending. Pick the 2-3 lowest-scoring cases.
2. **Minimise** — For each low-score case, read the requirement description and the generated case alongside. Compare what the requirement provides against what the case uses.
3. **Hypothesise** — Did the LLM ignore a rule? Misunderstand the requirement? Was the prompt instruction unclear about using symbolic parameters vs inventing values?
4. **Instrument** — Check the corresponding prompt file: is the rule present? Is it clear? Is it buried mid-prompt where a 7B model's attention decays?
5. **Fix** — Modify the prompt to address the root cause. Follow the modification rules in [REFERENCE.md](REFERENCE.md)
6. **Regression-test** — Before committing, re-run auto-scoring on a few previously passing cases to ensure the prompt change doesn't break what already worked

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
| `optimization/cli.py` | Batch generation CLI (--sample + --requirement-set) |
| `optimization/generate_case_html.py` | Checklist evaluation engine (v2 Section 3 hard gates) + case display report |
| `optimization/generate_report.py` | HTML evaluation report (checklist + Missing Info Hard Gates + Manual Review) |
| `optimization/manual_review.py` | Manual review score loading, weighted calc, hard gates, summary |
| `optimization_runs/checklist_v2.md` | Current checklist (v2 with [HARD] / [WARNING] items) |
| `optimization_runs/requirement_sets/prompt_eval_v1.json` | Prompt Evaluation Set V1 (30 entries, machine-readable) |
| `prompts/*.system.html` | Prompt templates to optimize |
| `optimization_runs/log/` | Run artifacts (git-ignored) |
| `optimization_runs/README.md` | Full protocol documentation |
| `docs/prompt-quality-optimization.md` | Optimization plan, rubric, phases, acceptance criteria |

## Checklist evolution

The checklist itself is iteratively improved. v1 (35 items) was created first. After 5 rounds of optimization, overlapping items were merged, misplaced items corrected, and the coverage methodology was rewritten — producing v2 with 6 new/replaced Section 3 items ([HARD] and [WARNING] gates for missing information detection). If the checklist needs revision, update `checklist_v2.md` and keep `CHECKLIST` dict in `generate_case_html.py` in sync.
