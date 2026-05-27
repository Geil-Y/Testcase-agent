# Implementation Spec: Deterministic Prompt Debug Report CLI

## Context

We are building a GEPA-inspired, human-in-the-loop prompt debugging workflow
for the Testcase-agent project.

Important documents:

- `docs/prompt-debugging/case-generation-philosophy.md`
- `docs/prompt-debugging/prompt-debug-review-loop.md`
- `docs/prompt-debugging/prompt-debug-report-format.md`

These documents define the authority order and report format. The
implementation must follow them.

This is not full GEPA. The report generator must not call an LLM, must not
modify prompt files, and must not choose a winning patch.

## Goal

Implement a deterministic CLI that reads one completed optimization/evaluation
round and generates a Markdown prompt debug report.

Target command:

```bash
python -m optimization.prompt_debug_report --round-dir <path-to-round-dir>
```

Default output:

```text
<round-dir>/prompt_debug_report.md
```

Optional output:

```bash
python -m optimization.prompt_debug_report \
  --round-dir <path-to-round-dir> \
  --output <path-to-report.md>
```

Use this real round for manual verification:

```text
C:\Users\Administrator\.config\superpowers\worktrees\Testcase-agent\codex-split-analysis-minimal-experiment\optimization_runs\log\20260523_eval
```

## Scope

Create:

```text
optimization/prompt_debug_report.py
tests/test_prompt_debug_report.py
```

Do not modify generation prompts.

Do not modify pipeline behavior.

Do not call any LLM.

Do not edit or depend on the experimental split-analysis pipeline.

## Inputs

The CLI reads these files from `--round-dir`.

Required:

```text
summary.json
generated_cases.json
hardrule_evaluation.json
```

Optional:

```text
deepseek_evaluation.json
```

If optional DeepSeek data is missing, the report should still generate with
`insufficient_data` or `not available` text.

## Output

Generate Markdown matching the structure in:

```text
docs/prompt-debugging/prompt-debug-report-format.md
```

Required sections:

1. Executive Summary
2. Run Metrics
3. Top Failure Clusters
4. Philosophy Regression Checks
5. Representative Cases
6. Prompt Root-Cause Hypotheses
7. Patch Candidates
8. Human Review Checklist

## Deterministic Aggregations

### 1. Run Metrics

Read from `summary.json`, `generated_cases.json`, `hardrule_evaluation.json`,
and optional `deepseek_evaluation.json`.

Include:

- Total requirements.
- Total generated cases.
- Case count distribution.
- Hard-rule pass rate.
- Hard-rule fail count ranking.
- Retry count.
- Exhausted retry count.
- DeepSeek total requirements evaluated, errors, overall weighted score.
- DeepSeek dimension averages if available.

### 2. Hard-Rule Fail Ranking

From `hardrule_evaluation.json`, use:

```json
item_fail_counts
```

Sort descending by fail count.

Also include these known item descriptions if present:

```text
2.1.1: Known signal names referenced in cases match requirement wording; no unsupported signal-name variants.
2.1.2: No invented identifiers outside selected requirement or accepted test basis.
3.2.1: Missing signal/threshold/timing/state/observation must be marked with [NEEDS REVIEW].
3.2.3: Do not add unnecessary [NEEDS REVIEW] when requirement semantics are complete.
3.3.2: Missing timing placeholder should be placed in a standalone wait step.
4.1.1: Timing wait and execution action should be separate steps.
4.1.4: Action should not contain pass/fail judgment or intent narration.
5.1.1: normal_behavior case should describe normal functional trigger and response.
```

If other item IDs appear, show the ID and count even if description is unknown.

### 3. Requirements Where All Cases Failed

From `hardrule_evaluation.json` cases:

For each requirement, count:

- Total cases.
- Cases with zero failures.
- Cases with failures.

List requirements where:

```text
passed_cases == 0
```

Include dominant failure item counts for each requirement.

### 4. Retry / Exhausted Summary

From `generated_cases.json`:

For each case, inspect optional:

```json
case["retry"]
```

Aggregate:

- Total retried cases.
- Total exhausted cases.
- Requirements with retried cases.
- Requirements with exhausted cases.

### 5. Missing Category Mismatch Summary

From `generated_cases.json`:

Each requirement may have:

```json
expected_missing_categories
analysis.missing_info_items[].category
```

Compute expected set vs actual set.

Report:

- Total requirements with exact match.
- Total mismatches.
- Mismatches grouped by evaluation bucket.
- Top mismatch examples.

A mismatch means:

```python
set(expected_missing_categories) != set(actual_missing_categories)
```

Ignore empty or missing category strings.

### 6. Case Count Distribution

From `generated_cases.json`:

Compute:

- Distribution of case count per requirement.
- Average cases per requirement.
- Requirements with high case count.

For the first version, define high case count as:

```text
case_count >= 5
```

### 7. DeepSeek Low Dimension Summary

If `deepseek_evaluation.json` exists, report:

- Overall weighted score.
- Dimension averages.
- Dimensions below 3.0.
- Worst requirements by weighted score, for example lowest 10.
- Unscored requirements if `generated_cases.json` contains requirement keys
  missing from DeepSeek requirements.

Case-level DeepSeek notes can be used for representative case summaries if
easy, but do not overcomplicate v1.

### 8. Failure Clusters

Generate deterministic clusters from available signals.

Implement at least these clusters.

#### `missing_info_false_negative`

Evidence:

- Hard-rule item `3.2.1` failures.
- `expected_missing_categories` is non-empty but actual missing categories are
  empty or missing expected categories.

Related philosophy:

- Missing Information Philosophy.
- Information Integrity.

#### `missing_info_false_positive`

Evidence:

- Hard-rule item `3.2.3` failures.
- `expected_missing_categories` is empty but actual missing categories are
  non-empty.

Related philosophy:

- Missing Information Philosophy.
- Anti-Patterns.

#### `action_judgment_mixing`

Evidence:

- Hard-rule item `4.1.4`.

Related philosophy:

- Action and Expected Boundary.

#### `wait_action_not_separated`

Evidence:

- Hard-rule item `4.1.1`.
- Hard-rule item `3.3.2`.

Related philosophy:

- Action and Expected Boundary.
- Executability Philosophy.

#### `case_count_inflation`

Evidence:

- Requirements with `case_count >= 5`.

Related philosophy:

- Case Splitting Philosophy.
- Coverage Value.

#### `low_executability`

Evidence:

- DeepSeek `executability` average below 3.0.
- Case-level or requirement-level low executability if available.

Related philosophy:

- Executability Philosophy.

#### `low_automation_readiness`

Evidence:

- DeepSeek `automation_readiness` average below 3.0.

Related philosophy:

- Executability Philosophy.
- Coverage Value.

For each cluster, output:

- ID.
- Title.
- Severity.
- Related philosophy principle.
- Evidence summary.
- Affected requirements.
- Representative cases.
- Opposite failure risk.

Severity guidance:

- High: affects hard gate or dimension average below 2.5, or many
  requirements.
- Medium: affects several cases but is not dominant.
- Low: minor or sparse.

Keep this simple and deterministic.

### 9. Philosophy Regression Checks

Use statuses:

```text
observed
possible
not_detected
insufficient_data
```

Map deterministic evidence to checks:

- `[NEEDS REVIEW] misuse risk`: observed if `3.2.1` or `3.2.3` failures exist.
- `Action/expected boundary risk`: observed if `4.1.1`, `4.1.4`, or `3.3.2`
  failures exist.
- `Coverage volume risk`: observed if any requirement has `case_count >= 5`.
- `Executability risk`: observed if DeepSeek executability average is below
  3.0; possible if DeepSeek is missing.
- `Metric-gaming risk`: possible if high case count and low
  coverage/executability coexist.
- `Information honesty risk`: observed if `2.1.1`, `2.1.2`, or `3.2.1`
  failures exist.
- `Traceability risk`: use DeepSeek `requirement_alignment` average below 3.0
  if available; otherwise insufficient_data.
- `Natural-language preservation risk`: insufficient_data for v1 unless bare
  marker detection is implemented.

### 10. Representative Cases

Select deterministic representative cases.

Prefer in order:

1. Cases from requirements where all cases failed.
2. Cases with retry exhausted.
3. Cases from high-severity clusters.
4. Cases from worst DeepSeek weighted requirements.
5. Cases with multiple hard-rule failures.

Limit to about 10 representative cases.

Each entry should include:

- Requirement key.
- Evaluation bucket.
- Case index.
- Case title.
- Selection reason.
- Hard-rule failures.
- Retry attempts and exhausted status if present.
- Related cluster IDs.

### 11. Root-Cause Hypotheses

For v1, output structured placeholders.

Example:

```markdown
## Prompt Root-Cause Hypotheses

Deterministic v1 does not infer final prompt root causes.
Use the failure clusters and representative cases above for human review.

| ID | Related Cluster | Suspected Prompt Area | Evidence | Opposite Failure Risk | Confidence |
| --- | --- | --- | --- | --- | --- |
```

You may fill obvious suspected prompt areas from cluster mapping, but do not
claim certainty.

### 12. Patch Candidates

For v1, output conservative placeholders only.

Do not write full prompt rewrites.

Example:

```markdown
## Patch Candidates

No patch is automatically recommended in deterministic v1.
Use the checklist below before accepting any manual patch.

| ID | Target Cluster | Protected Principle | Representative Target Cases | Representative Opposite Cases | Human Decision |
| --- | --- | --- | --- | --- | --- |
```

## Tests

Use TDD.

Add:

```text
tests/test_prompt_debug_report.py
```

Test at least:

1. `load_round()` reads required files and handles missing DeepSeek.
2. Hard-rule fail ranking sorts descending.
3. All-fail requirements are detected.
4. Retry/exhausted counts are aggregated.
5. Missing category mismatches are computed correctly.
6. Case count distribution and high-count requirements are computed.
7. Report renderer includes all required section headings.
8. CLI writes the output file.

Use small temp JSON fixtures. Do not rely on the real `20260523_eval` path in
tests.

## Verification Commands

Run focused tests:

```bash
python -m pytest tests/test_prompt_debug_report.py
```

Run full test suite if feasible:

```bash
python -m pytest
```

Known issue: the current project may have a pre-existing failure in:

```text
tests/test_claude_evaluator.py::test_user_prompt_contains_requirement_group_test_basis
```

If that still fails and no new failures are introduced, report it as
pre-existing.

Then generate the real report manually:

```bash
python -m optimization.prompt_debug_report \
  --round-dir C:\Users\Administrator\.config\superpowers\worktrees\Testcase-agent\codex-split-analysis-minimal-experiment\optimization_runs\log\20260523_eval
```

Expected output:

```text
C:\Users\Administrator\.config\superpowers\worktrees\Testcase-agent\codex-split-analysis-minimal-experiment\optimization_runs\log\20260523_eval\prompt_debug_report.md
```

## Non-Goals

Do not:

- Call an LLM.
- Edit prompts.
- Implement GEPA optimization.
- Choose prompt winners.
- Alter generation pipeline.
- Alter evaluation logic.
- Fix unrelated tests.
- Modify existing user changes unless needed for this feature.

## Expected Final Summary

Report:

- Files added or changed.
- Tests run and results.
- Path to generated prompt debug report.
- Any known pre-existing test failure.
