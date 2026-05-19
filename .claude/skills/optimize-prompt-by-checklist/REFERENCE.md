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

### Category 3: NEEDS REVIEW Usage (2 items)
Placeholder only for truly missing info. Must be placed at the exact position where the value belongs (action or expected).

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
- `CHECKLIST` — dict mapping item IDs to (description, category)
- `STANDARD_PRECONDITION` / `STANDARD_POSTCONDITION` — expected unified text
- `evaluate_case(case, req_info, global_data)` — returns list of failed item IDs

Each checklist item is a heuristic check:
- **1.1.x**: String emptiness / placeholder checks on case fields
- **2.1.1**: Signal name substring match in expected results
- **2.2.1**: Threshold substring match in expected results
- **2.2.2**: Regex for invented numeric values (e.g. `3.7V`, `50°C`) not in known parameters
- **3.1.1**: `[NEEDS REVIEW]` presence without missing info
- **3.2.1**: `[NEEDS REVIEW]` position in action/expected vs other fields
- **4.1.1**: Wait + non-null expected in same step (merged wait/verify)
- **4.1.2**: Duplicate action strings
- **4.2.1-4.2.3**: Expected result quality heuristics
- **6.1.1-6.1.2**: Keyword match against standard precondition/postcondition
- **6.1.3**: BMS-as-actor detection (tester should be the actor)
- **5.2.x**: NOT automatically checked (require human/Claude judgment)

Note: Items 5.1.x (coverage dimension matching) are WARNING level and not checked automatically. Items 5.2.x (equivalence class / boundary) are hard items but also require judgment — the automated check only applies heuristics.

## Keeping checklist and code in sync

The `CHECKLIST` dict in `generate_case_html.py` must match `checklist_v2.md`. When the checklist is updated:
1. Update `checklist_v2.md` with the new/modified items
2. Update `CHECKLIST` dict in `generate_case_html.py` if items are added/removed/renamed
3. Update `evaluate_case()` logic if evaluation criteria change
4. Run a smoke test on existing `generated_cases.json` to verify the new evaluation works
