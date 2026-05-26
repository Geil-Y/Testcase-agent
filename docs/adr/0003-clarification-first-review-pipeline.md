# ADR-0003: Clarification-First Review Pipeline

**Date:** 2026-05-24
**Status:** Accepted

## Context

The existing generation pipeline (`analyze_and_plan → generate_case → self_check`)
has a single-pass LLM flow with no structured human review. A 7B model cannot
reliably judge its own ambiguity, leading to invented behavior, missed missing
information, and inconsistent case quality.

## Decision

Replace the old generation pipeline with a clarification-first, confidence-routed,
human-reviewable pipeline. The new flow is:

```
decompose_requirement → clarification review → plan_case_intents → intent review → write_case → evaluate
```

Each stage separates LLM generation from human review. LLMs produce structured
JSON artifacts with confidence drivers. Humans review and decide. Code validates
decisions and advances the pipeline.

## Rationale

- A 7B model lacks the judgment to self-critique reliably. Splitting generation
  from review prevents the model from approving its own errors.
- Confidence routing (green/blue/orange/red) gives reviewers prioritization
  signals without the model making binding decisions.
- Pattern tags and Review Memory accumulate human decisions over time, providing
  historical support without granting authority.
- The code/prompt boundary is preserved: code owns plumbing and workflow
  orchestration; prompts own generation philosophy and semantic judgment.

## Consequences

- Old generation prompt files (`analyze_and_plan.*`, `generate_case.*`, `self_check.*`)
  are removed from the new workflow.
- `self_check` is out of scope for phase 1.
- New prompts: `decompose_requirement.*`, `plan_case_intents.*`, `write_case.*`.
- New CLI commands replace the old generation entry point.
- Review Memory introduces SQLite dependency.
