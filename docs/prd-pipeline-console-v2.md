## Problem Statement

The ABC pipeline (LLM-A analyze test basis → LLM-B plan case intents → LLM-C generate cases) currently runs only via CLI (`run_eval_batch.py`) with no interactive UI. Importing requirements, running pipeline stages, reviewing LLM outputs, and viewing generated test cases all require command-line operations and manual file inspection. The old Pipeline Console and Review Pipeline were deleted during the ABC refactor, leaving no visual interface for the pipeline.

## Solution

Build **Pipeline Console v2** — a local web UI backed by SQLite, with a React/Vite frontend. It provides:

- Excel requirement import with persistent storage
- Searchable/filterable requirement list
- Per-requirement pipeline runs with configurable per-stage human review
- Visual review of LLM-A TestBasis items with inline source-text highlighting
- Side-by-side view of Case Intents and generated Test Cases
- Checklist v2 evaluation results

## User Stories

1. As a test engineer, I want to import BMS requirements from an Excel file, so that I can start the pipeline without manually preparing JSON input files
2. As a test engineer, I want to see all imported requirements in a searchable list, so that I can quickly find a specific requirement among thousands
3. As a test engineer, I want to filter requirements by status (New / Pending / Reviewed), so that I can focus on what needs attention
4. As a test engineer, I want to press `/` to focus the search bar, so that I can search without using the mouse
5. As a test engineer, I want to create a new pipeline run for a selected requirement, so that I can start generating test cases
6. As a test engineer, I want to configure which LLM stages require human review before creating a run, so that I can balance review thoroughness against pipeline speed
7. As a test engineer, I want auto-approved stages to chain automatically, so that I don't have to click "advance" for each one
8. As a test engineer, I want to see all Extracted TestBasis items organized by their five canonical sections (signals, thresholds, timing, states, observations) in a sidebar, so that I can quickly scan what the LLM found
9. As a test engineer, I want to click a TestBasis item and see a modal editor that shows the original requirement text with the relevant excerpt highlighted, so that I can verify correctness without switching context
10. As a test engineer, I want to edit an item's status (known / needs_review), content, and missing need, so that I can correct or supplement the LLM's extraction
11. As a test engineer, I want my edits to TestBasis items to override the LLM-A output and become the authority for downstream stages, so that corrections propagate to case intents and test cases
12. As a test engineer, I want to see Case Intents paired with their corresponding Test Case in a single card group, so that I can verify the 1:1 intent-to-case mapping at a glance
13. As a test engineer, I want each case group to have a clear visual boundary (left accent border, shadow, spacing), so that I can easily distinguish between different cases
14. As a test engineer, I want to see test case details including title, objective, precondition, postcondition, and numbered steps with action/expected columns, so that I can evaluate the quality of generated test cases
15. As a test engineer, I want to see [NEEDS REVIEW] markers highlighted in test case steps, so that I can immediately spot where the LLM lacked information
16. As a test engineer, I want to run checklist v2 evaluation on generated cases, so that I can measure quality against the 34-item hard-rule checklist
17. As a test engineer, I want to create multiple runs for the same requirement, so that I can compare results across different pipeline configurations
18. As a test engineer, I want to press Esc to close any modal or return to the home page, so that navigation feels fast and predictable
19. As a developer tuning prompts, I want to set all three stages to auto-approve without review, so that the pipeline runs straight through and I can iterate on prompts quickly
20. As a test engineer, I want a calm, clean, light-themed interface with readable font sizes and generous spacing, so that I can work for long sessions without eye strain

## Implementation Decisions

### Data Storage
- SQLite database (`pipeline_console.db`) at project root as the single source of truth for the Console
- All LLM artifacts (test basis items, case intents, test cases with steps) stored in normalized relational tables
- CLI batch workflow (`run_eval_batch.py`) continues to use file-based JSON output — unaffected by the database
- See ADR-0006 for rationale

### Pipeline Architecture
- `run_pipeline()` split into three independently callable stage functions: `run_llm_a()`, `run_llm_b()`, `run_llm_c()`
- Each stage function takes a Requirement + provider, reads needed inputs from DB, writes outputs to DB
- The original `run_pipeline()` is preserved for CLI backward compatibility
- All LLM calls are synchronous (no async job queue for MVP)

### Review Configuration
- Per-run `review_required` setting: a list of stages `[a, b, c]` that require human review
- Any subset is valid: `[]` (full auto), `[a]`, `[b]`, `[c]`, `[a,b]`, `[a,c]`, `[b,c]`, `[a,b,c]`
- Locked at Run creation time, cannot be changed after
- Auto-advance: when advancing past a stage and the next N consecutive stages are all auto-approve, the backend chains them in a single synchronous POST /advance response

### API Contract
- `GET /api/v1/console/requirements` — list with `?q=&status=&offset=&limit=`
- `POST /api/v1/console/requirements/import` — multipart Excel upload, returns parsed count
- `GET /api/v1/console/requirements/:id` — single requirement with associated runs
- `POST /api/v1/console/runs` — create run with `{"requirement_id": N, "review_required": ["a","b","c"]}`, executes LLM-A sync
- `GET /api/v1/console/runs/:id` — run status + all artifacts (sections, items, intents, cases)
- `POST /api/v1/console/runs/:id/advance` — advance to next stage, auto-chain if configured
- `POST /api/v1/console/runs/:id/evaluate` — run checklist v2 evaluation
- `PUT /api/v1/console/runs/:id/sections/:section/items/:item_id` — edit item
- `POST /api/v1/console/runs/:id/sections/:section/items` — add item
- `DELETE /api/v1/console/runs/:id/sections/:section/items/:item_id` — delete item

### UI Design
- Light theme, Linear-inspired aesthetic (clean, calm, fast)
- Home page: searchable table with status filter chips (All / New / Pending / Reviewed), `/` key to focus search
- Workspace: 300px sidebar (requirement card + 5 collapsible test basis sections + blocking gaps textarea) + flexible main area (test cases)
- Test cases displayed as card groups: intent bar (with coverage dimension badge) paired directly above case body (title with Case N tag, objective, pre/postcondition, numbered steps table)
- Case groups separated by left accent border (3px blue), subtle shadow, 28px gaps
- Item editing via centered modal overlay: requirement text at top with source excerpt highlighted (light blue background, like highlighter pen), followed by status dropdown, content textarea, need textarea
- [NEEDS REVIEW] markers rendered as highlighted inline spans within step text

## Testing Decisions

### What makes a good test
- Test external behavior, not implementation details
- For backend: test API endpoints return correct HTTP codes and response shapes; test pipeline stage functions with mock providers (following `test_generate_pipeline.py` patterns)
- For frontend: test component rendering with given props; test user interactions trigger expected callbacks

### Modules to test
- **Pipeline stage functions** (`run_llm_a/b/c`): mock LLM provider, verify correct DB writes and error handling. Prior art: `tests/test_generate_pipeline.py` uses `CapturingProvider` pattern
- **Console API routes**: FastAPI TestClient, verify endpoints return expected response shapes, handle missing resources (404), handle invalid inputs (422)
- **Console DB store**: unit test CRUD operations against an in-memory or temp-file SQLite
- **Advance engine**: unit test auto-chain logic with different review configurations
- **Frontend components**: React Testing Library for key components (Home page search/filter, Workspace rendering, Modal interaction)

### Prior art
- `tests/test_generate_pipeline.py` — mock provider pattern for testing pipeline stages
- `tests/test_json_parser.py` — input validation pattern
- `tests/test_abc_evaluator.py` — evaluator testing pattern

## Out of Scope

- User authentication or multi-user support
- Async/background job execution for LLM calls
- Batch execution of multiple requirements at once
- Review Memory (pattern-based learning from past reviews)
- HTML report generation within Console (CLI `run_eval_batch.py` handles this)
- Migration of existing JSON artifact runs into the database
- Dark mode toggle (light theme only for MVP)
- Mobile responsive layout (desktop-first)

## Verification Strategy

**All development and testing uses mock LLM providers. Real LLM calls are NOT required to verify any issue.**

The `CapturingProvider` pattern from `tests/test_generate_pipeline.py` is the standard approach: a mock that returns pre-canned JSON/HTML responses and records the prompts it received. Set `TCASE_LLM_PROVIDER=mock` to use `MockProvider` from `testcase_agent/provider/mock.py`. Pipeline stage functions are verified by checking correct DB writes and prompt rendering, not LLM output quality.

## Further Notes

- The UI prototype is at `prototype/pipeline-console-v2.html` — it validates the layout, interaction patterns, and visual design. The implementation should match its look and feel.
- ADR-0006 documents the SQLite decision.
- The existing `run_pipeline()` function in `pipeline/generate.py` must remain functional for CLI backward compatibility.
- The old `pipeline_console/` and `review_pipeline/` directories were deleted in commit 193b9b8 and should not be restored.
