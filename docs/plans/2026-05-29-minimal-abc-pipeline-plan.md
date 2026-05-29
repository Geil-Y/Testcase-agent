# Minimal ABC Pipeline Plan

## Goal

Restore a small baseline generation pipeline based on the legacy linear flow, with only one intentional addition:

```text
Requirement
  -> LLM-A JSON typed test basis
  -> LLM-B JSON case intents
  -> LLM-C HTML test case
  -> HTML parser
  -> generated_cases.json
  -> evaluator
```

This is a baseline quality path, not the future Review Console path.

## Scope

Implement the minimal ABC path beside the current review pipeline first. Batch evaluation should be able to run this path directly. The current review pipeline, Review Console, Review Memory, confidence routing, reason codes, fact references, and default-human-approve behavior should stay out of this path.

Do not delete the review pipeline in this change. Freeze it while the ABC path is brought back to a passing quality line.

## Design Rules

- Code owns orchestration, provider calls, parsing, validation, artifact writing, and evaluator wiring.
- Prompts own semantic extraction and writing behavior.
- Each LLM call has one job.
- Requirement description is the only generation authority in the minimal path.
- Supplementary info is not passed to LLM-A, LLM-B, or LLM-C in this baseline path.
- LLM-C must not receive fact IDs, confidence values, routing labels, review decisions, reason codes, memory hints, or raw review artifacts.
- Prompts should avoid concrete domain examples, invented numeric samples, and fixed step templates.
- Schema constraints should be explicit enough to prevent parser crashes. For enum fields, prompts must require string enum values only.

## Data Contracts

### LLM-A: Typed Test Basis JSON

Purpose: extract only the requirement-owned basis for testing.

Required top-level fields:

- `requirement_key`: string
- `allowed_signals`: list of strings
- `allowed_thresholds`: list of strings
- `allowed_timing`: list of strings
- `allowed_states`: list of strings
- `allowed_observations`: list of strings
- `missing_info`: list of objects

`missing_info` object fields:

- `category`: one of `signal`, `threshold`, `timing`, `state`, `observation`
- `description`: string

No severity field is needed in this minimal path unless a concrete consumer exists. If severity is later reintroduced, it must be a string enum such as `low`, `medium`, `high`, or `critical`, never a number.

### LLM-B: Case Intent JSON

Purpose: produce the minimum supported case intents from the requirement and typed test basis.

Required top-level fields:

- `requirement_key`: string
- `case_intents`: list of objects

`case_intents` object fields:

- `intent_id`: string
- `coverage_dimension`: string enum
- `intent_text`: string

Use a short, stable coverage enum. Keep it broad enough to avoid forcing fake cases:

- `normal_behavior`
- `boundary_or_threshold`
- `fault_or_protection`
- `state_transition`
- `observability`

LLM-B prompt behavior is already prepared from the legacy LLM1 `coverage_plan` policy. It keeps the old default case-splitting behavior for OR branches, relevant modes, boundary trigger/non-trigger conditions, and timed mature/not-mature conditions. The only added planning constraint is that multiple expected results or evidence points for the same required response should stay in the same case intent.

### LLM-C: HTML Test Case

Purpose: write exactly one executable-style test case for one approved intent.

Input should contain only:

- requirement key
- requirement description
- one case intent
- coverage dimension
- typed allow-lists from LLM-A
- missing information from LLM-A

Output remains the existing `<testcase>` HTML shape parsed by `parse_generated_case`.

Writer rules to preserve:

- Do not invent numeric values, signal names, thresholds, timing values, states, diagnostics, observations, HIL channel names, tool commands, or bench configuration.
- Preserve requirement relations symbolically instead of replacing them with representative numbers.
- Do not force every case into three steps.
- An action is an operation performed by the tester or test system.
- An expected result is the pass/fail condition after an action and any required wait/event.
- Do not put the required BMS response in the same step that applies the triggering stimulus.
- After a trigger stimulus, add a separate wait/event/evidence step before judging the BMS response when the requirement implies delayed behavior.
- `Check` and `Verify` are not action verbs.
- Evidence collection verbs such as read, record, observe, monitor, or capture are valid only when they describe collection, not pass/fail judgment.
- Use `[NEEDS REVIEW]` only for missing signal, threshold, timing, state, or observation information.

## Files To Change

- Prompt files are already prepared for the minimal ABC path. Implementation should wire these prompts as-is and should not redesign, expand, or rewrite prompt behavior during the first minimal rollback implementation.

- `src/testcase_agent/pipeline/generate.py`
  - Restore old linear orchestration shape.
  - Replace the old two-call flow with A JSON, B JSON, C HTML.
  - Keep public compatibility for `RequirementInput`, `GenerationResult`, `run_pipeline`, and `regenerate_case` where practical.

- `src/testcase_agent/parser/json_parser.py`
  - Add JSON parsing for `TestBasis` and `PlannedCaseIntent`.
  - Keep JSON parsing separate from `html_parser.py`.
  - Reject invalid enum values instead of silently coercing them.

- `src/testcase_agent/parser/html_parser.py`
  - Keep focused on LLM-C HTML parsing.
  - Avoid adding review-pipeline concepts here.

- `prompts/analyze_test_basis.system.html`
- `prompts/analyze_test_basis.user.html`
  - LLM-A prompt pair.
  - User prompt should include requirement fields only.
  - No further prompt design change is required in the implementation pass.

- `prompts/plan_case_intents.system.html`
- `prompts/plan_case_intents.user.html`
  - LLM-B prompt pair.
  - Input should be requirement plus typed test basis.
  - No further prompt design change is required in the implementation pass.

- `prompts/generate_case.system.html`
- `prompts/generate_case.user.html`
  - LLM-C HTML writer prompt pair.
  - Remove review metadata, fact references, supplementary info, and fixed step assumptions from writer input.
  - No further prompt design change is required in the implementation pass.

- `run_eval_batch.py`
  - Add a selectable minimal ABC batch path, for example `--pipeline minimal`.
  - Keep the existing review path available as `--pipeline review`.
  - Default can be `minimal` while the baseline is being restored.

## Implementation Steps

1. Add parser models and tests for LLM-A JSON.
   - Put tests in `tests/test_json_parser.py` or another focused JSON parser test file.
   - Test valid typed basis parsing.
   - Test invalid `missing_info.category` rejection.
   - Test fenced JSON is accepted if current providers commonly wrap output.

2. Add parser models and tests for LLM-B JSON.
   - Keep these with the LLM-A parser tests.
   - Test valid case intent parsing.
   - Test invalid `coverage_dimension` rejection.
   - Test empty intent list is treated as a pipeline error.

3. Wire existing LLM-A prompts.
   - Prompt content is already done before implementation starts.
   - Do not redesign or expand the prompt during implementation.
   - Ensure `run_pipeline` passes only `requirement_key` and `description`.

4. Wire existing LLM-B prompts.
   - Prompt content is already done before implementation starts.
   - Do not redesign or expand the prompt during implementation.
   - Ensure `run_pipeline` passes only the selected requirement and typed test basis.

5. Rework `run_pipeline`.
   - Call LLM-A and parse typed basis.
   - Call LLM-B and parse intents.
   - For each intent, call LLM-C and parse HTML.
   - Store parse failures as generation failures with enough error text for debugging.
   - Do not import or call review-pipeline stages.

6. Wire existing LLM-C prompts.
   - Prompt content is already done before implementation starts.
   - Do not redesign or expand the prompt during implementation.
   - Keep writer input narrow: requirement, one intent, typed allow-lists, and missing information.

7. Add minimal batch evaluation mode.
   - Write `generated_cases.json` in the artifact shape expected by the evaluator.
   - Run the existing evaluator.
   - Keep review pipeline mode available but not used for the baseline batch.

8. Run focused verification.
   - `.\.venv\Scripts\python.exe -m pytest tests\test_json_parser.py tests\test_html_parser.py tests\test_generate_pipeline.py -q`
   - Add and run a focused batch-mode test if `run_eval_batch.py` is changed.
   - Run a 10-requirement minimal batch and inspect generated artifacts manually.

## Acceptance Checks

- LLM-A and LLM-B outputs are JSON.
- LLM-C output is HTML.
- `generated_cases.json` is still the evaluator input artifact.
- Minimal batch does not invoke clarification review or case intent review.
- Generated cases contain no `[fact-...]` references.
- Writer prompts contain no confidence, routing, reason code, review memory, or review decision fields.
- Supplementary info does not appear in A/B/C prompts for the minimal path.
- No obvious invented representative numeric values appear in generated cases.
- Actions do not start with `Check` or `Verify`.
- Trigger and expected BMS response are not collapsed into the same step when a wait/event is needed.

## Out Of Scope

- Review Console.
- Review Memory.
- Human approval UI.
- Confidence routing.
- Reason code registry.
- Fact-reference traceability.
- Rich prompt debugging reports.
- Schema expansion beyond the fields listed above.

## Risk Notes

- The old pipeline prompt must not be copied verbatim. Its linear structure is useful, but old fixed-step and concrete-example wording caused quality issues.
- Adding too much schema now recreates the current complexity problem. Only add fields with a direct consumer.
- If batch quality is still poor after this reset, inspect A/B/C artifacts separately before adding features.
