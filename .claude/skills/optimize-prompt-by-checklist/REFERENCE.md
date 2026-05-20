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

- Automated checklist failures (hard-rule evaluator).
- AI Review Scores (`deepseek_evaluation.json`, `chatgpt_evaluation.json`, rendered in `cases_report.html`) — semantic judgments by DeepSeek and ChatGPT against checklist_v2.md.
- Missing Information Hard Gates.
- Manual Review Scores, when present.
- Sanitizer provenance in `generated_cases.json`.

Manual Review Scores are the preferred acceptance signal when available.
Next preference is AI Review Scores (semantic, covers items hard rules cannot).
Without either, use automated checklist pass rate as the fallback signal.

### AI Review vs Hard-Rule

The `cases_report.html` compares hard-rule, DeepSeek, and ChatGPT scores per case
with evaluator badge cards. Key differences to watch:

- Items where AI is significantly stricter (Δ < -5%): hard rules may be missing
  semantic violations (e.g., generic titles, vague expected results).
- Items where AI is significantly looser (Δ > +5%): AI may be lenient on
  mechanical rules (e.g., word count checks).
- AI covers cross-case items (5.2.x) that hard rules skip entirely.
- AI notes provide concrete reasons for each fail, useful for diagnosis.

## Manual Review Scoring

Score on 8 dimensions, 1-5 scale. `coverage_value` is scored once per
requirement over the full generated case set; the other seven dimensions
are scored per case.

| Dimension | Weight | Score high when... | Score low when... |
| --- | ---: | --- | --- |
| Requirement Alignment | 20% | Case clearly addresses the requirement's intent and scope | Case is off-target, misinterprets, or addresses a different concern |
| Information Integrity | 20% | Missing semantics are correctly marked with `[NEEDS REVIEW]`; no invented values | Case invents missing signal, threshold, timing, state, or observation |
| Executability | 15% | A HIL engineer can run the procedure without rewriting it | Steps are vague or require rewriting |
| Observability | 15% | Expected results are concrete and judgeable from BMS outputs | Expected results are vague or read-only |
| Pass/Fail Clarity | 10% | Pass/fail criteria are explicit and unambiguous | Criteria are implied, fuzzy, or missing |
| Coverage Value | 10% | The requirement-level case set verifies meaningful behavior or risk | The cases are trivial, redundant, or off-target |
| State & Environment | 5% | Initial state and environment setup are explicit and complete | Preconditions lack necessary state/bench details |
| Automation Readiness | 5% | Steps are atomic, well-structured, and directly automatable | Steps are narrative or require human interpretation |

Hard gates (implemented by shared evaluator in `optimization/evaluator.py`):

- `information_integrity < 3` makes the case unacceptable.
- A case that should contain `[NEEDS REVIEW]` but does not is unacceptable (3.2.1).
- A case that invents missing signal, threshold, timing, state, or observation
  semantics is unacceptable (3.2.2).
- Unnecessary `[NEEDS REVIEW]` on a complete requirement is a warning (3.2.3).

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
