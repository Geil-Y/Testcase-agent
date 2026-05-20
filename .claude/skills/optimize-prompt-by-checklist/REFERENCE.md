# Reference: Checklist Optimization

For workflow facts, read `docs/optimization-workflow.md`. This file contains
only prompt-editing and review guidance that should not depend on current set
size or CLI selection behavior.

## Prompt Modification Rules

When modifying prompts to address checklist failures:

1. Do not change the LLM#1 -> LLM#2 two-stage structure.
2. Do not change the HTML output format.
3. Keep `analyze_and_plan.system.html` within its intended small-model budget.
4. Keep `generate_case.system.html` within its intended small-model budget.
5. Reinforce ignored rules before adding new rules.
6. Put critical constraints near the beginning and end of the system prompt.
7. Avoid contradictions with existing prompt rules.
8. Keep changes compact enough for a 7B-8B local model.
9. Diagnose concrete failures before editing prompts.

## Evaluation Guidance

The current evaluator and workflow are documented in
`docs/optimization-workflow.md`.

When reading a report, separate:

- Automated checklist failures.
- Missing Information Hard Gates.
- Manual Review Scores, when present.
- Sanitizer provenance in `generated_cases.json`.

Manual Review Scores are the preferred acceptance signal when available.
Without them, use automated checklist pass rate as the fallback signal.

## Manual Review Scoring

Score each generated case on four dimensions from 1 to 5:

| Dimension | Weight | Score high when... | Score low when... |
| --- | ---: | --- | --- |
| Executability | 20% | A HIL engineer can run the procedure without rewriting it | Steps are vague or require rewriting |
| Observability | 20% | Expected results are concrete and judgeable from BMS outputs | Expected results are vague or read-only |
| Coverage Value | 20% | The case verifies meaningful requirement behavior or risk | The case is trivial, redundant, or off-target |
| Missing Information Detection | 40% | Missing requirement semantics are marked with `[NEEDS REVIEW]` | The case invents missing values or behavior |

Hard gates:

- `missing_information_detection < 3` makes the case unacceptable.
- A case that should contain `[NEEDS REVIEW]` but does not is unacceptable.
- A case that invents missing signal, threshold, timing, state, or observation
  semantics is unacceptable.
- Unnecessary `[NEEDS REVIEW]` on a complete requirement is a warning unless it
  blocks executability.

## Diagnosis Loop

For each round:

1. Pick the lowest-quality cases.
2. Compare source requirement text against generated case content.
3. Identify whether the failure is prompt clarity, model capability, data
   ambiguity, or evaluator limitation.
4. Change the smallest prompt text that addresses the cause.
5. Re-evaluate before making further prompt changes.

## Keeping Docs In Sync

When workflow behavior changes:

1. Update `docs/optimization-workflow.md`.
2. Update this reference only if prompt-editing or scoring guidance changes.
3. Avoid restating current set size, checklist version, or CLI selection
   semantics here.
