# Review Pipeline

Simplified A/B/C reviewed pipeline for test case generation (ADR-0005).

Replaces the legacy facts/ambiguities/confidence-routing flow with a
three-stage extraction → planning → writing pipeline with explicit review gates.

## Flow

```
Input requirements
  → LLM-A Test Basis Extractor (extract)
  → extracted_test_basis.json
  → human review (Accept/Edit/Add/Remove/Block Run)
  → reviewed_extracted_test_basis.json
  → LLM-B Case Intent Planner (plan-intents)
  → case_intents.json
  → human review (Accept/Edit/Add/Remove/Block Run)
  → reviewed_case_intents.json
  → LLM-C Case Writer (generate-cases)
  → generated_cases.json
  → human review (Accept/Edit/Regenerate)
  → reviewed_cases.json
```

## Commands

| Command | Input | Output |
|---|---|---|
| `extract --input <req.json> --out <dir>` | Requirements JSON | `extracted_test_basis.json` |
| `accept-extraction --run-dir <dir>` | Extracted basis | `reviewed_extracted_test_basis.json` |
| `plan-intents --run-dir <dir>` | Reviewed extraction | `case_intents.json` |
| `accept-intents --run-dir <dir>` | Case intents | `reviewed_case_intents.json` |
| `generate-cases --run-dir <dir>` | Reviewed artifacts | `generated_cases.json` |
| `accept-cases --run-dir <dir>` | Generated cases | `reviewed_cases.json` |
| `regenerate --run-dir <dir> --requests <json>` | Reviewed artifacts + comment | Updated `reviewed_cases.json` |

## Design Rules

- Each LLM output and its `reviewed_*` counterpart use the same schema.
- Downstream stages read only reviewed artifacts.
- supplementary_info is not passed to any LLM prompt.
- LLM-B and LLM-C must not discover new missing information.
- LLM-C may only emit `[NEEDS REVIEW]` for unresolved items from reviewed extraction.
- Review Memory is removed from the main pipeline path.
- Legacy artifacts (clarification_review.json, etc.) are unsupported; old runs must be regenerated.
