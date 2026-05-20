# Optimization Runs

This directory stores prompt optimization artifacts: checklists, executable
requirement sets, and generated run outputs.

The source of truth for workflow facts is the skill file at
[`.claude/skills/optimize-prompt-by-checklist/skill.md`](../.claude/skills/optimize-prompt-by-checklist/skill.md).
Use that document for the current checklist version, Prompt Evaluation Set size,
CLI selection semantics, sanitization behavior, and evaluator ownership.

## Directory Layout

```text
optimization_runs/
├── checklist_v1.md
├── checklist_v2.md
├── README.md
├── requirement_sets/
│   └── prompt_eval_v1.json
└── log/
    └── <run-name>/
        ├── round_01/
        │   ├── prompts/
        │   ├── sampled_requirements.json
        │   ├── summary.json
        │   ├── generated_cases.json
        │   ├── hardrule_evaluation.json
        │   ├── deepseek_evaluation.json
        │   ├── chatgpt_evaluation.json
        │   ├── evaluation_report.html
        │   └── cases_report.html
        └── ...
```

## Run Outputs

Each round directory may contain:

| File | Meaning |
| --- | --- |
| `prompts/` | Archived prompt files used for the round |
| `sampled_requirements.json` | Requirements selected for the round |
| `summary.json` | Generation summary and optional requirement-set metadata |
| `generated_cases.json` | Generated requirements/cases, quality data, and sanitize provenance |
| `manual_review_scores.json` | Optional human/agent 8-dimension review scores |
| `hardrule_evaluation.json` | Per-evaluator hard-rule evaluation data |
| `deepseek_evaluation.json` | Per-evaluator DeepSeek 8-dimension evaluation data |
| `chatgpt_evaluation.json` | Per-evaluator ChatGPT evaluation data |
| `evaluation_report.html` | Checklist, hard-gate, and optional manual-review summary |
| `cases_report.html` | Unified main report combining all evaluators with per-case display |

## Notes

- Generated run logs under `optimization_runs/log/` are git-ignored.
- Update the skill file first when workflow behavior changes.
