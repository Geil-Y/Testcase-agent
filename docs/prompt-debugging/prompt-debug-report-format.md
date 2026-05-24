---
name: prompt-debug-report-format
description: Output format for the first prompt debug report
status: draft
created: 2026-05-23
---

# Prompt Debug Report Format

This document defines the first report format for the prompt debugging
workflow. It is intentionally limited to deterministic aggregation and human
review support.

The first implementation must not call an LLM, modify prompt files, or decide
which patch should be applied.

## Inputs

The report generator reads a completed evaluation round directory containing:

- `summary.json`
- `generated_cases.json`
- `hardrule_evaluation.json`
- `deepseek_evaluation.json` when available

It also references:

- `docs/prompt-debugging/case-generation-philosophy.md`
- `docs/prompt-debugging/prompt-debug-review-loop.md`
- Archived prompt files from the round when present

## Output

The report is a Markdown file written to the round directory unless the caller
provides another output path.

Default filename:

```text
prompt_debug_report.md
```

## Required Sections

### 1. Executive Summary

Short summary of:

- Total requirements and generated cases.
- Hard-rule pass rate.
- DeepSeek weighted score when available.
- Most important failure clusters.
- Most important philosophy regression risks.
- Whether the run is suitable for prompt patch review.

### 2. Run Metrics

Include:

- Total requirements.
- Total generated cases.
- Cases per requirement distribution.
- Hard-rule total passed, total failed, and pass rate.
- Retry count and exhausted count when available.
- DeepSeek evaluated requirements, errors, overall weighted score, and
  dimension averages when available.

### 3. Top Failure Clusters

Each cluster must include:

- Cluster ID.
- Title.
- Severity: high, medium, or low.
- Related philosophy principle.
- Related hard-rule items or DeepSeek dimensions.
- Affected requirement keys.
- Affected case count.
- Evidence summary.
- Representative cases to inspect.
- Opposite-failure risk to consider before patching.

Initial deterministic clusters:

- `missing_info_false_negative`
- `missing_info_false_positive`
- `bare_needs_review_marker`
- `invented_concrete_evidence`
- `case_count_inflation`
- `precondition_negative_explosion`
- `observation_method_split`
- `action_judgment_mixing`
- `missing_evidence_collection`
- `unbounded_wait`
- `low_executability`
- `low_automation_readiness`

The first implementation does not need to detect every cluster perfectly.
It should report only clusters that can be supported by available artifacts.

### 4. Philosophy Regression Checks

For each check, report status as:

- `observed`
- `possible`
- `not_detected`
- `insufficient_data`

Checks:

- Traceability risk.
- Information honesty risk.
- Natural-language preservation risk.
- `[NEEDS REVIEW]` misuse risk.
- Case splitting risk.
- Action/expected boundary risk.
- Executability risk.
- Coverage volume risk.
- Metric-gaming risk.

Each observed or possible risk must cite evidence.

### 5. Representative Cases

List cases that a human should inspect before changing prompts.

Each representative case entry must include:

- Requirement key.
- Evaluation bucket when available.
- Case index.
- Case title.
- Why it was selected.
- Related cluster IDs.
- Hard-rule failures.
- Retry/exhausted metadata when available.
- DeepSeek notes when available.

Prefer cases that:

- Come from requirements where every case failed hard rules.
- Have retry exhausted.
- Represent high-severity clusters.
- Show a philosophy issue, not only a formatting issue.
- Could expose the opposite failure of a likely patch.

### 6. Prompt Root-Cause Hypotheses

This section contains hypotheses, not conclusions.

Each hypothesis must include:

- ID.
- Related cluster ID.
- Suspected prompt file.
- Suspected prompt clause or topic.
- Evidence.
- Why the prompt may cause the behavior.
- Opposite-failure risk.
- Confidence: low, medium, or high.

The first deterministic implementation may leave this section as a structured
placeholder when it cannot support a hypothesis without LLM or human review.

### 7. Patch Candidates

Patch candidates are suggestions for human review. They must not be applied
automatically.

Each candidate must include:

- ID.
- Target prompt file.
- Target cluster.
- Proposed change.
- Protected philosophy principle.
- Supporting evidence.
- Representative target-failure cases.
- Representative opposite-failure cases.
- Risk if wrong.
- Human decision: accept, reject, revise, or defer.

The first deterministic implementation may leave this section empty or produce
only conservative placeholders. It must not invent full prompt rewrites.

### 8. Human Review Checklist

Include a checklist for the reviewer:

- Is the target failure real?
- Does the proposed change preserve `case-generation-philosophy.md`?
- Does the change avoid benchmark-specific wording?
- Did we inspect at least one target-failure case?
- Did we inspect at least one opposite-failure risk case?
- Could this patch increase `[NEEDS REVIEW]` misuse?
- Could this patch increase case count inflation?
- Could this patch reduce executability or automation readiness?
- Is the patch small enough to evaluate in the next run?

## Cluster Schema

```text
id: string
title: string
severity: high | medium | low
philosophy_principle: string
related_hardrule_items: list[string]
related_deepseek_dimensions: list[string]
affected_requirements: list[string]
affected_case_count: integer
evidence_summary: string
representative_cases: list[case_ref]
opposite_failure_risk: string
```

## Case Reference Schema

```text
requirement_key: string
evaluation_bucket: string
case_index: integer
case_title: string
selection_reason: string
cluster_ids: list[string]
hardrule_failures: list[string]
retry_attempts: integer
retry_exhausted: boolean
deepseek_notes: list[string]
```

## Patch Candidate Schema

```text
id: string
target_prompt: string
target_cluster: string
proposed_change: string
protected_principle: string
supporting_evidence: string
representative_target_cases: list[case_ref]
representative_opposite_cases: list[case_ref]
risk_if_wrong: string
human_decision: accept | reject | revise | defer | undecided
```

## First Implementation Scope

The first implementation should generate:

- Run metrics.
- Hard-rule fail ranking.
- Requirements where all generated cases failed hard rules.
- Retry and exhausted counts.
- Missing-category expected versus actual mismatch summary.
- Case count distribution and high-count requirements.
- DeepSeek low dimension summary when available.
- Representative cases selected by deterministic rules.
- Structured placeholders for root-cause hypotheses and patch candidates.

## Explicit Non-Goals

The first implementation must not:

- Call an LLM.
- Rewrite prompts.
- Choose the best patch.
- Treat aggregate score as the main quality target.
- Decide that a project document is correct when it conflicts with
  `case-generation-philosophy.md`.
- Replace human review of representative cases.
