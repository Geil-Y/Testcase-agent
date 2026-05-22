---
name: eval-prompt-and-commit
description: Run full 35-case prompt evaluation via DeepSeek and commit current prompts with key metrics. Use when user wants to evaluate+baseline prompts, "evaluate and commit", "跑一轮评估并提交", or benchmark prompt changes against the Prompt Evaluation Set V1.
---

# Eval Prompt and Commit

One-shot evaluation of current prompts against the 35-entry Prompt Evaluation Set V1, followed by a git commit of prompt files with key metrics in the message.

## Workflow

### 1. Pick output directory

Use a dated name: `optimization_runs/log/YYYYMMDD_eval/`. If the name already exists, append `_2`, `_3`, etc.

### 2. Run evaluation

```powershell
python -m optimization.cli run `
  --requirement-set optimization_runs/requirement_sets/prompt_eval_v1.json `
  --no-retry `
  --eval `
  --output-dir optimization_runs/log/<run-name>
```

This generates cases for all 35 requirements without LLM regeneration retries
and runs DeepSeek 8-dimension scoring concurrently (batched, 5 reqs per API call).
Use `--no-retry` by default to skip expensive per-case LLM regeneration; only the
final quality gate and DeepSeek review run.

### 3. Wait for completion

The command prints progress per requirement. Wait until the final line:

```
Done. 35 requirements → N cases, 0 errors
```

### 4. Extract metrics

Parse these from the output:

| Metric | Source in output |
|--------|-----------------|
| Total cases | `Done. 35 requirements → N cases` |
| Passed / Failed | `Round 1: XP / YF (Z%)` |
| Pass rate | Same line, the `Z%` value |
| Weighted score | `DeepSeek evaluation completed (weighted=X.X)` |
| Log folder | The `--output-dir` value (last component) |

### 5. Commit prompt files

Only stage files under `prompts/`. Do NOT commit generated reports, JSON files, or round directories.

```bash
git add prompts/
git commit -m "$(cat <<'EOF'
<type>(prompts): <brief summary of what changed or "baseline after evaluation">

Run: <log-folder-name>
N cases, quality gate: XP / YF (Z%)
DeepSeek weighted: W.W

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

Use Conventional Commits type (`fix`, `feat`, `refactor`) based on what changed in prompts. If no prompt changes were made (eval-only baseline), use `chore(prompts): baseline evaluation`.

### 6. Report

Print a one-line summary to the user:

```
Run <log-folder-name>: N cases, XP/YF passed (Z%), DeepSeek weighted W.W. Committed prompts as <commit-hash>.
```

## Rules

- Always run all 35 requirements — no `--limit` unless user explicitly asks.
- Do NOT commit `generated_cases.json`, `deepseek_evaluation.json`, `cases_report.html`, or any file under `optimization_runs/log/`.
- Only commit changes under `prompts/` (and `src/` or `optimization/` if code was also changed).
- If the evaluation fails partway, report the error and ask whether to retry or commit partial results.
