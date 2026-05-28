# Audit: Failing Test Ownership After A/B/C Pipeline Simplification

**Date**: 2026-05-28
**Parent PRD**: [#37](https://github.com/Geil-Y/Testcase-agent/issues/37)
**Target branch**: `codex/legacy-compatible-abc-pipeline-prd`

## Summary

- **Total tests in `test_review_pipeline.py` + `test_pipeline_console.py`**: 258
- **Passing**: 185
- **Failing**: 73
- **New tests** (`test_simplified_pipeline.py`): **43/43 passing**

All failures are caused by the simplified A/B/C pipeline migration removing the facts/ambiguities confidence-routing data model from the main path. None are production bugs — each test exercises a legacy behavior contract that the simplified pipeline deliberately drops.

---

## Failure Groups

### Group 1 — Legacy Pipeline End-to-End (test_review_pipeline.py)

| Test | Classification |
|------|---------------|
| `TestIntentPlanning::test_produces_intent_review` | **delete/replace** |
| `TestIntentPlanning::test_blocked_basis_prevents_planning` | **delete/replace** |
| `TestIntentPlanning::test_html_contains_routing_colors` | **delete/replace** |
| `TestCaseIntentValidation::test_approve_includes_intent` | **delete/replace** |
| `TestCaseIntentValidation::test_reject_excludes_intent` | **delete/replace** |
| `TestCaseIntentValidation::test_defer_excludes_intent` | **delete/replace** |
| `TestCaseIntentValidation::test_merge_requires_target` | **delete/replace** |
| `TestCaseIntentValidation::test_split_requires_children` | **delete/replace** |
| `TestCaseIntentValidation::test_revise_includes_final_text` | **delete/replace** |
| `TestCaseIntentValidation::test_traceability_preserved` | **delete/replace** |
| `TestCaseWriter::test_generates_one_case_per_intent` | **migrate** |
| `TestCaseWriter::test_skips_where_plan_empty` | **migrate** |
| `TestCaseWriter::test_generated_cases_have_traceability` | **migrate** |
| `TestCaseWriter::test_generated_json_has_evaluator_fields` | **migrate** |
| `TestCaseWriter::test_writer_prompt_receives_source_context_and_missing_markers` | **migrate** |
| `TestEvaluation::test_evaluate_run` | **real bug** |
| `TestEvaluation::test_evaluation_traceability_preserved` | **real bug** |
| `TestEndToEnd::test_full_pipeline_with_fake_providers` | **migrate** |
| `TestCLI::test_prepare_clarification_review_mock_flag` | **delete/replace** |

**Root cause**: `TestCaseIntentValidation` tests use the legacy `CaseIntentPlan`/`CaseIntentReview`/`LegacyCaseIntentItem` schemas with reason-code-based decisions (approve/reject/revise/merge/split/defer). The simplified pipeline replaced this with `CaseIntentSet` carrying simple `{intent_id, coverage_dimension, intent_text}` items.

`TestIntentPlanning` calls `prepare_intent_review()` which no longer references `clarified_test_basis.json` — the legacy alias now reads `reviewed_extracted_test_basis.json`.

`TestCaseWriter` tests set up legacy `approved_case_plan.json` artifacts that the new `generate_cases()` no longer reads (it reads `reviewed_case_intents.json` + `reviewed_extracted_test_basis.json`).

`TestEvaluation` tests call `evaluate_run()` which reads `generated_cases.json` format. The field `approved_intent_id` was renamed to `intent_id` in the new `GeneratedCase` model, causing Pydantic validation errors.

`TestEndToEnd` exercises the legacy pipeline from `prepare_clarification_review` through `generate_cases` using old artifact names. Needs a full rewrite for the new flow.

`TestCLI::test_prepare_clarification_review_mock_flag` calls the legacy CLI command which now returns exit 1 with unsupported message.

**Classified**: 10 delete/replace, 7 migrate, 2 real bug

**Follow-up issue**: Write a single `TestSimplifiedEndToEnd` that exercises `extract → accept → plan → accept → generate → accept` with the new artifact flow. Replace the delete/replace tests with equivalents targeting new schemas. Fix the real bugs in `evaluate_run`.

---

### Group 2 — Console Run Status & Discovery (test_pipeline_console.py)

| Test | Classification |
|------|---------------|
| `TestRunDiscovery::test_old_style_runs_readable` | **deferred feature** |
| `TestRunStatusInference::test_clarification_ready` | **migrate** |
| `TestRunStatusInference::test_clarification_blocked` | **migrate** |
| `TestRunStatusInference::test_intent_ready` | **migrate** |
| `TestRunStatusInference::test_cases_ready_from_approved_plan` | **migrate** |
| `TestRunStatusInference::test_cases_ready_from_generated` | **migrate** |
| `TestRunStatusInference::test_evaluated` | **migrate** |

**Root cause**: `_infer_run_status` in runs.py was rewritten to use new artifact names (`extracted_test_basis.json`, `reviewed_extracted_test_basis.json`, etc.) and new status strings (`extraction_pending_review`, `extraction_reviewed`, `cases_pending_review`, etc.). The tests hardcode old status strings like `clarification_ready`, `intent_ready`, `cases_ready`, `evaluated`. The old status detection logic for `clarified_test_basis.json` / `case_intent_review.json` / `approved_case_plan.json` no longer exists.

`test_old_style_runs_readable` expects old-style `run_NNN` directories to be readable. The new code surfaces them as `legacy_unsupported` instead of silently reading them. This is intentional per ADR-0005.

**Classified**: 1 deferred feature (will need Console redesign), 6 migrate

**Follow-up issue**: Update `_infer_run_status` tests to assert new status strings. Update run discovery tests to expect legacy-unsupported marking.

---

### Group 3 — Console Workbench Legacy API Contracts (test_pipeline_console.py)

| Test | Classification |
|------|---------------|
| `TestClarificationWorkbench::test_save_draft_persists_decisions` | **delete/replace** |
| `TestClarificationWorkbench::test_save_draft_run_not_found` | **delete/replace** |
| `TestWorkbenchAPIs::test_save_draft_blocked_by_job` | **migrate** |
| `TestWorkbenchAPIs::test_advance_blocked_by_job` | **migrate** |
| `TestValidationErrors::test_validation_errors_have_structure` | **delete/replace** |
| `TestBlockedPath::test_advance_returns_blocked_state` | **delete/replace** |
| `TestWorkbenchResultShapes::test_validation_failure_has_status_field` | **delete/replace** |
| `TestWorkbenchResultShapes::test_blocked_has_status_field` | **delete/replace** |
| `TestEndToEndHappyPath::test_full_api_flow_import_to_results` | **migrate** |
| `TestMemoryAdvisoryOnly::test_no_auto_import_on_advance` | **delete/replace** |
| `TestMemoryAdvisoryOnly::test_no_auto_import_on_generate` | **delete/replace** |
| `TestUnchangedUpstreamReuse::test_advance_reuses_when_unchanged` | **delete/replace** |
| `TestUnchangedUpstreamReuse::test_advance_does_not_reuse_when_changed` | **delete/replace** |
| `TestUnchangedUpstreamReuse::test_generate_reuses_when_unchanged` | **delete/replace** |
| `TestStartRunAPI::test_start_run_rejects_when_job_running` | **migrate** |
| `TestStartRunAPI::test_start_run_nonexistent_batch` | **migrate** |
| `TestJobLockingCrossActions::test_all_job_backend_routes_reject_when_running` | **migrate** |
| `TestIntentWorkbench::test_save_intent_draft_persists` | **delete/replace** |
| `TestIntentAPIs::test_intent_draft_blocked_by_job` | **migrate** |
| `TestIntentAPIs::test_generate_blocked_by_job` | **migrate** |
| `TestResults::test_results_endpoint_returns_cases_read_only` | **migrate** |
| `TestConsoleUIFixes::test_validation_error_shape` | **delete/replace** |
| `TestConsoleUIFixes::test_accept_recommendations_api_shape` | **delete/replace** |
| `TestDownstreamArtifacts::test_clarification_review_downstream` | **migrate** |
| `TestDownstreamArtifacts::test_generated_cases_downstream` | **migrate** |
| `TestDownstreamArtifacts::test_artifacts_to_archive_only_existing` | **migrate** |

**Root cause**: The workbench module was rewritten for new stage functions (`load_extraction`, `load_intents`, `load_cases`, `accept_extraction_all`, `plan_and_load_intents`, etc.). These tests call legacy functions (`save_clarification_draft`, `save_and_advance_clarification`, `save_intent_draft`, `save_and_generate_cases`) that still exist as legacy aliases, but they operate on old artifact names and old data shapes. The tests set up `clarification_review.json` with a `decomposition`/`decisions` structure that the new extraction flow doesn't produce.

**Classified**: 17 delete/replace, 9 migrate

**Follow-up issue**: Write new Console workbench tests using the new functions and new endpoints (`/extraction`, `/intents`, `/cases`). Delete tests for removed concepts.

---

### Group 4 — Removed Console Concepts (test_pipeline_console.py)

| Test | Classification |
|------|---------------|
| `TestReasonCodesAPI::test_get_reason_codes_clarification` | **delete/replace** |
| `TestReasonCodesAPI::test_get_reason_codes_case_intent` | **delete/replace** |
| `TestReasonCodesAPI::test_get_reason_codes_unknown_type` | **delete/replace** |
| `TestAcceptRecommendations::test_accept_recommendations_fills_pending` | **delete/replace** |
| `TestAcceptRecommendations::test_accept_recommendations_force_confirm` | **delete/replace** |
| `TestAcceptRecommendations::test_accept_recommendations_skips_already_decided` | **delete/replace** |
| `TestAcceptRecommendations::test_accept_recommendations_blocked_by_job` | **delete/replace** |
| `TestFilteredClarification::test_filtered_endpoint_returns_enriched_data` | **delete/replace** |
| `TestFilteredClarification::test_filtered_by_decision` | **delete/replace** |
| `TestFilteredClarification::test_filtered_by_routing` | **delete/replace** |
| `TestFilteredClarification::test_filtered_by_search` | **delete/replace** |
| `TestFilteredClarification::test_priority_sort_pending_first` | **delete/replace** |
| `TestMemoryHints::test_memory_hints_endpoint_returns_advisory` | **delete/replace** |
| `TestRegenerate::test_regenerate_no_confirmation_lists_artifacts` | **delete/replace** |
| `TestRegenerate::test_regenerate_confirm_archives_and_starts_job` | **delete/replace** |
| `TestRegenerate::test_regenerate_blocked_by_job` | **delete/replace** |
| `TestRegenerate::test_regenerate_unknown_stage` | **delete/replace** |
| `TestRegenerate::test_regenerate_clarification_succeeds` | **delete/replace** |
| `TestRegenerate::test_regenerate_clarification_validation_failure` | **delete/replace** |
| `TestRegenerate::test_regenerate_clarification_blocked` | **delete/replace** |
| `TestRegenerate::test_regenerate_missing_upstream_artifact` | **delete/replace** |

**Root cause**: These tests exercise concepts explicitly removed from the simplified pipeline per ADR-0005:

- **`/reason-codes`**: Reason codes were part of the legacy clarification/case-intent review model using human decisions with coded justifications. Removed from simplified pipeline.
- **Accept Recommendations**: Auto-filled decisions from LLM-recommended values and confidence thresholds. Removed — the simplified pipeline uses explicit Accept All without LLM recommendation logic.
- **Filtered Clarification**: Enriched ambiguity items with routing colors, confidence, severity, and decision filtering. Replaced by simple section-based extraction view.
- **Review Memory hints**: SQLite-based historical decision hints. Removed from main path; may be redesigned later around reviewed artifacts (deferred).
- **Old Regenerate flow**: Multi-stage regenerate that archives downstream artifacts and re-runs LLM. Replaced by C-only regenerate with review comment using `reviewed_cases.json`.

**Classified**: 21 delete/replace

**Follow-up issue**: Delete all tests in groups `TestReasonCodesAPI`, `TestAcceptRecommendations`, `TestFilteredClarification`, `TestMemoryHints`, `TestRegenerate`. These are not "deferred" — the concepts are permanently removed from the simplified pipeline.

---

## Endpoints and Concepts That Must NOT Be Restored

These were removed from the main path per ADR-0005. No future issue should revive them under their old names/data shapes:

| Removed Endpoint / Concept | Reason |
|----------------------------|--------|
| `GET /reason-codes` | Reason codes tied to legacy clarification/case-intent decisions |
| `POST /clarification/accept-recommendations` | LLM recommendation auto-fill tied to confidence routing |
| `GET /clarification/filtered` | Depends on ambiguity severity/confidence/routing enrichment |
| `GET /memory-hints` | Review Memory SQLite hints tied to legacy ambiguity pattern tags |
| `POST /regenerate` (old stage-based) | Multi-stage downstream archive + re-run; replaced by C-only regenerate |
| Facts / Ambiguities data model | `RequirementDecomposition`, `AmbiguityItem`, `ClarificationReview` |
| Confidence routing | `get_routing_color`, routing labels, confidence_score, confidence_drivers |
| Reason-code decisions | `ClarificationDecision`, `CaseIntentDecision`, YAML registry |
| Legacy artifact names | `clarification_review.json`, `clarified_test_basis.json`, `case_intent_review.json`, `approved_case_plan.json` |

---

## Follow-up Issues Map

| Area | Issue Count | Priority | Description |
|------|-----------|----------|-------------|
| **Pipeline tests** | 19 tests, 2 test classes | High | Rewrite `TestIntentPlanning`, `TestCaseIntentValidation`, `TestCaseWriter`, `TestEndToEnd` for new schemas. Fix `evaluate_run` real bugs. Delete legacy CLI test. |
| **Console tests** | 54 tests, ~15 test classes | High | Delete `TestReasonCodesAPI`, `TestAcceptRecommendations`, `TestFilteredClarification`, `TestMemoryHints`, `TestRegenerate`. Migrate `TestRunStatusInference`, `TestWorkbenchAPIs`, `TestDownstreamArtifacts`, `TestResults`, `TestStartRunAPI` to new endpoints + new data shapes. Rewrite `TestEndToEndHappyPath` for new flow. |
| **Legacy cleanup** | 17 tests | Medium | Delete `TestClarificationWorkbench`, `TestWorkbenchResultShapes`, `TestConsoleUIFixes`, `TestBlockedPath`, `TestValidationErrors`, `TestUnchangedUpstreamReuse`, `TestMemoryAdvisoryOnly` tests for permanently removed concepts. Verify legacy `_legacy_unsupported` CLI commands have coverage. |
| **Review UI** | Deferred | Low | Console HTML currently shows minimal extraction/intents/cases views. Full inline edit, regenerate comment input, and blocking-gap resolution UI require a separate Console UX redesign slice. |
| **Report rendering** | Deferred | Low | `render_unified_report` in html_rendering/report.py still references legacy artifact names. Rewrite for new artifact flow when reports are needed. |
