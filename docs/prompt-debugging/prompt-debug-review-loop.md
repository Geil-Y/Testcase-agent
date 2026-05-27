---
name: prompt-debug-review-loop
description: Human-in-the-loop GEPA-inspired prompt debugging workflow
status: draft
created: 2026-05-23
---

# Prompt Debug Review Loop

This document defines the workflow for diagnosing prompt quality problems
without allowing an optimizer or evaluator to rewrite the generation
philosophy.

The workflow is GEPA-inspired: it uses generated outputs, evaluator feedback,
and failure traces to propose prompt improvements. It is not full GEPA:
prompt changes are not applied automatically, and metrics do not choose the
winning prompt.

## Purpose

Help a human improve prompts by turning evaluation artifacts into:

- Failure clusters.
- Philosophy regression checks.
- Prompt root-cause hypotheses.
- Small prompt patch candidates.
- Representative cases for manual review.
- Opposite-failure risk cases.

The workflow must make prompt review more evidence-based without encouraging
metric gaming.

## Authority Order

Use this order when artifacts disagree:

1. `docs/prompt-debugging/case-generation-philosophy.md`
2. Human review judgment for representative cases.
3. `docs/good-testcase-definition.md`
4. `optimization_runs/scoring_rubrics.md`
5. Hard-rule and LLM evaluator metrics.

Existing project documents and evaluator metrics are diagnostic references,
not unquestionable authority. If a metric improvement conflicts with the case
generation philosophy, reject or revise the prompt change.

## Inputs

A prompt debug run reads one completed evaluation round:

- `summary.json`
- `generated_cases.json`
- `hardrule_evaluation.json`
- `deepseek_evaluation.json` when available
- `docs/prompt-debugging/case-generation-philosophy.md`
- Current prompt files, or archived prompt files from the round

The first implementation may run without an LLM. It should aggregate objective
signals and produce a structured Markdown report.

## Outputs

The report should be written as Markdown. It should not modify prompt files.

Required sections:

- Executive summary.
- Run metrics.
- Failure clusters.
- Philosophy regression checks.
- Prompt root-cause hypotheses.
- Patch candidates.
- Representative cases for human review.
- Next evaluation checklist.

## Failure Cluster Taxonomy

A failure cluster is a recurring quality pattern with evidence. It is not just
a failed checklist item.

Initial clusters:

- Missing-information false negative: the case needed `[NEEDS REVIEW]` but did
  not mark the missing semantic point.
- Missing-information false positive: the case marked `[NEEDS REVIEW]` where
  the selected requirement provided enough information.
- Bare marker: usable requirement wording was replaced by `[NEEDS REVIEW]`.
- Invented concrete evidence: the case introduced a signal, value, state,
  observation, DTC, CAN field, or tool capability not in the accepted test
  basis.
- Case count inflation: generated cases increased without distinct
  verification value.
- Precondition explosion: separate negative cases were created for listed
  preconditions whose variation did not change expected behavior.
- Observation-method split: cases were split by CAN/internal/log/measurement
  mechanism even though requirement behavior and acceptance criteria were the
  same.
- Action/judgment mixing: pass/fail judgment appeared in an action step.
- Missing evidence collection: expected result required evidence but the case
  did not identify how evidence could be observed or collected.
- Unbounded wait: timing or response wait lacked requirement-derived timing,
  event point, or `[NEEDS REVIEW]`.
- Low executability: steps were too abstract, multi-action, or dependent on
  hidden setup assumptions.
- Low automation readiness: the case was formally structured but hard to
  convert into executable test assets.

Each cluster should include:

- Affected requirements.
- Affected case indices.
- Related hard-rule items.
- Related DeepSeek dimensions or notes when available.
- Representative examples.
- Why the pattern matters under `docs/prompt-debugging/case-generation-philosophy.md`.

## Philosophy Regression Checks

The report should explicitly check whether generated cases or suggested prompt
changes violate the case generation philosophy.

Checks:

- Traceability: cases verify the selected requirement, not neighboring context.
- Information honesty: unsupported concrete details are not invented.
- Natural-language preservation: usable requirement wording is preserved.
- Proper `[NEEDS REVIEW]`: markers appear at exact missing semantic points and
  are not used defensively.
- Case splitting: new cases change expected behavior, pass/fail judgment, or
  evidence needed to prove the requirement.
- Action/expected boundary: actions describe operations or evidence
  collection, while expected results state judgments.
- Executability: known steps are concrete, ordered, and reviewable.
- Coverage value: the case set provides verification complementarity, not just
  volume.
- Metric gaming: cases do not look optimized for checklist or evaluator
  language rather than engineering value.

## Prompt Root-Cause Hypotheses

Root-cause hypotheses explain why a failure cluster may be caused by prompt
language.

Each hypothesis must state:

- The failure cluster.
- The suspected prompt file and clause.
- Evidence from generated cases.
- Why the prompt clause may lead to the observed behavior.
- What opposite failure might appear if the clause is changed.

Example:

```text
Cluster: Missing-information false positive
Prompt clause: classify missing observation whenever no concrete signal is named
Observed behavior: generated cases mark [NEEDS REVIEW] even when the requirement
states an observable natural-language outcome.
Opposite failure risk: the model may stop marking true observation gaps.
```

## Patch Candidate Format

Patch candidates are proposals for human review. They must not be applied
automatically.

Each patch candidate must include:

- ID.
- Target prompt file.
- Target failure cluster.
- Proposed prompt change.
- Supporting evidence.
- Philosophy principle protected.
- Expected benefit.
- What quality may get worse if this patch is wrong.
- Representative target-failure cases to inspect.
- Representative opposite-failure cases to inspect.
- Human decision: accept, reject, revise, or defer.

Patch candidates should be small. A patch should address one failure cluster
or one prompt ambiguity. Do not produce a full rewritten prompt as a patch.

## Representative Case Selection

For each major cluster, choose representative cases that make human review
efficient.

Prefer:

- A case from a requirement where all generated cases failed.
- A case with retry exhausted.
- A case with multiple related failures.
- A case whose DeepSeek note explains the quality problem clearly.
- A case that shows a philosophy violation, not only a checklist violation.

For every patch candidate, include at least:

- One case where the target failure occurs.
- One case where the patch could cause the opposite failure.

## Human Review Rules

The human reviewer decides whether a patch is accepted.

Accept only when:

- The target failure cluster is real.
- The patch protects or strengthens the case generation philosophy.
- Representative cases support the change.
- Opposite-failure risk is understood and acceptable.
- The patch is small enough to evaluate in the next run.

Reject or revise when:

- The patch improves a metric by weakening the philosophy.
- The patch is benchmark-specific.
- The patch encourages over-marking or under-marking `[NEEDS REVIEW]`.
- The patch encourages case count inflation.
- The patch hides low executability behind better structure.
- The patch rewrites too much prompt surface at once.

## Next Evaluation Checklist

After applying a human-approved patch, the next evaluation run should compare:

- Target failure cluster count.
- Hard-rule pass rate.
- Missing-category expected versus actual match.
- Case count distribution.
- Retry and exhausted counts.
- DeepSeek dimension averages and low-scoring requirements.
- Representative target-failure cases.
- Representative opposite-failure cases.
- Any new philosophy regression.

The patch should be kept only if it improves the target problem without
introducing a more important philosophy regression.

## Must Not Do

This workflow must not:

- Automatically edit prompt files.
- Select prompt patches solely by aggregate score.
- Treat hard-rule pass rate as the definition of quality.
- Treat DeepSeek notes as unquestionable authority.
- Optimize for the fixed evaluation set at the expense of general test-case
  quality.
- Produce large prompt rewrites as normal patch candidates.
- Hide project-document contradictions instead of surfacing them.
