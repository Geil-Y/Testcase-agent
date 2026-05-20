# Optimization Runs

This directory stores prompt optimization artifacts: checklists, executable
requirement sets, and generated run outputs.

The source of truth for workflow facts is
[`docs/optimization-workflow.md`](../docs/optimization-workflow.md). Use that
document for the current checklist version, Prompt Evaluation Set size, CLI
selection semantics, sanitization behavior, and evaluator ownership.

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
| `manual_review_scores.json` | Optional human/agent review scores |
| `evaluation_report.html` | Checklist, hard-gate, and optional manual-review report |
| `cases_report.html` | Per-case display report |

## Notes

- Generated run logs under `optimization_runs/log/` are git-ignored.
- Update `docs/optimization-workflow.md` first when workflow behavior changes.
