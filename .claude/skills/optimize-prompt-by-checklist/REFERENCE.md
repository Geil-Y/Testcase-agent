# Reference: Checklist Optimization

## Prompt modification rules

When modifying prompts to address checklist failures, obey these constraints:

### Architecture
- **Do NOT change** the LLM#1 → LLM#2 two-stage structure
- **Do NOT change** the HTML output format

### Token budgets
- `analyze_and_plan.system.html`: ≤ 800 tokens
- `generate_case.system.html`: ≤ 1200 tokens

### Modification strategy
1. **Reinforce ignored rules** — if the LLM ignores a rule, repeat it in the prompt's tail section rather than adding new rules
2. **U-shaped attention** — put the most critical constraints at the very beginning and very end of the system prompt (LLMs attend most to these positions)
3. **No contradictions** — new text must not conflict with existing rules
4. **Compress verbosity** — replace wordy expressions with compact ones to stay within token budget
5. **Record changes** — copy prompts into each round's `prompts/` directory so diffs are available

### What good prompt changes look like

Round 1 → Round 5 of `generate_case.system.html`:

| Problem | Round 1 approach | Round 5 fix |
|---------|-----------------|-------------|
| LLM invents "3.7V", "50°C" | No rule against it | `CRITICAL — Do NOT invent numeric values` at top |
| Null expected results | `Setup/wait steps may have null expected results` | `Every step MUST have a non-null expected result` |
| Merged wait+verify steps | No explicit separation rule | `Step 1 sets, Step 2 waits, Step 3 checks` |
| Inconsistent pre/postcondition | No fixed text | Explicit literal text with `ALL cases use this` |
| Rules buried mid-prompt | Rules in middle of prompt | `REMINDER` section at very end with key constraints |

## Checklist structure (v2)

### Category 1: Structural Integrity (6 items)
Non-empty fields (title, objective, precondition, postcondition, steps), traceability to requirement, correct HTML output.

### Category 2: Domain Correctness (3 items)
Signal names match requirement text, no invented identifiers (CAN IDs, etc.), no invented numeric thresholds — use symbolic parameter names.

### Category 3: NEEDS REVIEW Usage (6 items, with [HARD] / [WARNING] gates)

Five canonical missing semantic categories: signal, threshold, timing, state, observation. Does NOT cover HIL channels, tool commands, or bench config.

Hard gates:
- **3.2.1 [HARD]** — need missing semantics but case lacks `[NEEDS REVIEW]` → case unacceptable
- **3.2.2 [HARD]** — case invents missing signal/threshold/timing/state/observation → case unacceptable
- **3.2.3 [WARNING]** — requirement semantically complete but case adds unnecessary `[NEEDS REVIEW]` → penalized, not automatically severe

Position rules:
- **3.3.1** — `[NEEDS REVIEW]` only in action/expected, not title/objective/precondition/postcondition
- **3.3.2** — timing missing → `[NEEDS REVIEW]` placed in Wait action
- **3.3.3** — bare `[NEEDS REVIEW]` only; no `[NEEDS REVIEW: timing]` category suffix

### Category 4: Step Quality (5 items)
Timing wait and action in separate steps. No duplicate stimulus/wait steps. At least one concrete observable expected result. No vague expected results. No read/check-only expected without specific values.

### Category 5: Coverage Dimensions (3 hard + 5 warning)
**Hard items (5.2.x):** Equivalence class partitioning — trigger vs non-trigger, boundary values, orthogonal parameter/timing dimensions.
**Warning items (5.1.x):** Coverage dimension matching (normal_behavior, boundary_or_threshold, fault_or_protection, state_transition, observability) — guidance only, not pass/fail.

### Category 6: Test Engineering Depth (5 items)
Unified precondition/postcondition across all cases. Setup actions in steps, not precondition. Descriptive titles. One case = one requirement behavior. Don't merge multiple threshold scenarios into one case.

## How to evaluate a round

### Step 1: Run the evaluation script
Point `generate_report.py` at the round directory. It reads `generated_cases.json`, runs `evaluate_case()` from `generate_case_html.py` on every case, and produces `evaluation_report.html`.

### Step 2: Read the report
Open `evaluation_report.html`. Key sections:
- **Summary cards** — overall pass rate, pass/fail counts, delta from previous round
- **Category pass rates** — which categories are weakest
- **Worst-failing items** — top 10 items with lowest pass rate
- **All items table** — every checklist item with pass rate and failure count
- **Failed case samples** — specific cases with their failed item IDs

### Step 3: Diagnose root cause
For each top-failing item:
- Is it a prompt problem? (rule missing, unclear, or contradicted)
- Is it a model capability problem? (7B model simply can't do this reliably)
- Is it a data problem? (requirements lack signal names, making 2.1.1 impossible)

### Step 4: Prioritize fixes
Focus on items that:
1. Affect many cases (high failure count)
2. Are prompt-fixable (not inherent model limitations)
3. Don't require adding new rules (reinforce existing ones instead)

## How the evaluation engine works

`generate_case_html.py` defines:
- `CHECKLIST` — dict mapping item IDs to (description, category), synced with `checklist_v2.md`
- `evaluate_case(case, req_info, global_data)` — returns `(failed, warnings)` tuple
- `evaluate_missing_info_hard_gates(data)` — compares Prompt Evaluation Set expected vs actual missing categories
- `_enrich_req_info(req)` — extracts per-requirement context for evaluation

Each checklist item is a heuristic check:
- **1.1.x**: String emptiness / placeholder checks on case fields
- **2.1.1**: Signal name substring match in expected results
- **2.2.1**: Regex for invented numeric values (e.g. `3.7V`, `50°C`) not in known parameters
- **2.2.2**: Symbolic parameter names treated as valid (no deterministic check)
- **3.2.1 [HARD]**: Expected missing categories non-empty but case lacks `[NEEDS REVIEW]` in action/expected
- **3.2.2 [HARD]**: Threshold expected missing but case invents numeric values without `[NEEDS REVIEW]`
- **3.2.3 [WARNING]**: `[NEEDS REVIEW]` present when no expected missing categories → warning, not fail
- **3.3.1**: `[NEEDS REVIEW]` in title/objective/precondition/postcondition → fail
- **3.3.2**: Timing expected missing but `[NEEDS REVIEW]` not in Wait action → fail
- **3.3.3**: `[NEEDS REVIEW: category]` suffix pattern → fail
- **4.1.1 [WARNING]**: Wait + non-null expected in same step (merged wait/verify)
- **4.2.1-4.2.3**: Expected result quality heuristics
- **6.1.1-6.1.2**: Keyword match against standard precondition/postcondition
- **6.1.3**: BMS-as-actor detection (tester should be the actor)
- **5.2.x**: NOT automatically checked (require human/Claude judgment)

Note: Items 5.1.x (coverage dimension matching) are WARNING level and not checked automatically. Items 5.2.x (equivalence class / boundary) are hard items but also require judgment — the automated check only applies heuristics. WARNING items (3.2.3, 4.1.1) are tracked but do not count toward case pass/fail.

## Auto-scoring protocol (Claude Code as LLM-as-Judge)

When the user enables auto-scoring, Claude Code produces `manual_review_scores.json` by reading `generated_cases.json` and scoring each case. The implementation is in `optimization/manual_review.py`.

### Scoring workflow

1. Read `generated_cases.json` and parse requirements + cases.
2. For each requirement, read the `description` and `analysis` (signals, thresholds, timing, states, observations, missing_info_items).
3. For each case under that requirement, score on 4 dimensions (1-5).
4. Write `manual_review_scores.json` using the format defined in SKILL.md.
5. Re-run `generate_report()` — the Manual Review Scores section is automatically rendered.

### Scoring guidance

| Dimension | Score high when... | Score low when... |
|-----------|-------------------|-------------------|
| Executability (20%) | Step sequence is logical, actions are concrete, a HIL engineer could follow it directly | Steps are vague, rely on intent language, or miss necessary setup |
| Observability (20%) | Expected results name specific signals/states/DTCs with concrete values | Expected results are "system works correctly" or read-only without expected values |
| Coverage Value (20%) | Case exercises a meaningful threshold, boundary, state transition, or fault path | Case is trivial, redundant, or doesn't test the stated requirement behavior |
| Missing Info Detection (40%) | Every invented value is replaced with `[NEEDS REVIEW]`; gaps are flagged not filled | Case invents signals/thresholds/timing/states/observations the requirement didn't provide |

### Hard gates (applied before weighted score is accepted)

- `missing_information_detection < 3` → case is unacceptable
- Case should contain `[NEEDS REVIEW]` but does not → unacceptable
- Case invents missing signal/threshold/timing/state/observation → unacceptable
- Semantically complete requirement adds unnecessary `[NEEDS REVIEW]` → warning, not severe

These gates are implemented in `apply_hard_gates()` and rendered in the report.

### Token efficiency

Score **one requirement at a time**, not all cases at once. Read the requirement description, then all its cases, then output scores for those cases. This keeps each scoring turn focused and avoids context overflow.

A single scoring turn processes: requirement description (~200 words) + analysis metadata + N cases (N typically 1-4, ~150 words each). For a 30-entry Prompt Evaluation Set with ~90 cases, this is ~25-30 scoring turns.

## Keeping checklist and code in sync

The `CHECKLIST` dict in `generate_case_html.py` must match `checklist_v2.md`. When the checklist is updated:
1. Update `checklist_v2.md` with the new/modified items
2. Update `CHECKLIST` dict in `generate_case_html.py` if items are added/removed/renamed
3. Update `evaluate_case()` logic if evaluation criteria change
4. Run a smoke test on existing `generated_cases.json` to verify the new evaluation works
