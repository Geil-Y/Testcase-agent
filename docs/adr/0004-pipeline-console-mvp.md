# ADR-0004: Pipeline Console MVP

**Status:** Accepted

## Context

ADR-0003 deliberately kept main UI integration out of phase 1 and made JSON
artifacts the source of truth for the clarification-first review pipeline. The
next step is a local UI that makes review usable without turning the system into
a multi-user workflow platform or bypassing the pipeline artifacts.

## Decision

Build a local **Pipeline Console** as the phase 2 user entry point. The Console
imports requirements, lets the reviewer select one Requirement, creates one
**Active Run** for that Requirement, hosts the **Review Workbench** for
Clarification Review and Case Intent Review, advances validated pipeline stages,
and shows generated cases and evaluation results.

The MVP keeps run state in the existing artifact directory model. New runs use a
human-readable timestamped name based on the selected Requirement:

```text
YYYYMMDD_HHMMSS_run_<requirement_key>_<description_slug>
```

Existing `run_###` directories remain readable for compatibility, but new
Console and CLI runs should use the timestamped name.

## Consequences

- The Console API calls review pipeline stage functions directly; the CLI remains
  a script-oriented adapter over the same pipeline core.
- Pipeline Console is product code, not a throwaway prototype. Backend code lives
  under `src/testcase_agent/pipeline_console/`, with FastAPI integration from the
  existing application entry point.
- The legacy sandbox UI is removed rather than kept as a compatibility surface;
  new UI work targets Pipeline Console only.
- Pipeline Console replaces the sandbox-era API surface instead of living beside
  it. Console endpoints use the `/api/v1/console/...` namespace; legacy
  `/api/v1/import/*`, `/api/v1/generate/*`, `/api/v1/results/*`, and `/sandbox`
  endpoints are not retained for compatibility.
- The MVP supports importing many Requirements but advances exactly one Active
  Run at a time. Batch execution is deferred.
- `Start Run` writes a single-requirement `00_requirements.json`, runs
  `prepare_clarification_review(...)`, and opens Clarification Review.
- If a Requirement already has historical runs, the Console offers
  `Open Latest Run` and `Start New Run`; run ownership is determined from
  `00_requirements.json`, not from the directory name.
- The run workspace uses a fixed left stage navigation showing the current
  Requirement, Active Run, and stage status. The Requirements list stays on the
  Console home page and is not shown inside the run workspace.
- MVP run status is derived from active artifacts: `new`,
  `clarification_ready`, `clarification_blocked`, `intent_ready`,
  `cases_ready`, `evaluated`, or `failed`.
- Review pages provide `Save Draft` plus explicit action-chain buttons:
  `Save & Prepare Case Intent Review` and `Save & Generate Cases`.
- A `block` decision in Clarification Review stops the run before Case Intent
  Review.
- Results are read-only in the MVP. Corrections happen by revising upstream
  review decisions and regenerating downstream artifacts.
- When normalized upstream artifact content changes, downstream artifacts are
  archived before regeneration. If content is unchanged and downstream artifacts
  already exist, the Console opens them instead of rerunning LLM stages.
- Long-running stage actions run as a single local in-memory job with polling;
  editing and stage buttons are locked while a job is running.
- Real LLM mode is the default. Mock mode is only available through explicit
  developer configuration and must be visibly labeled.
- Review Memory import remains an explicit user action; the Console never writes
  Review Memory automatically.

## Considered Options

- **Review Workbench only:** rejected because the requested workflow includes
  importing requirements, creating runs, advancing stages, and viewing results,
  not just editing review decisions.
- **Batch-first console:** rejected for the MVP because queue state, retry,
  concurrency, and aggregate dashboards would distract from making the single
  review loop reliable.
- **Separate run database:** rejected for the MVP because artifact directories
  already provide durable, inspectable state and preserve CLI compatibility.
- **Shelling out to CLI from the API:** rejected because direct stage function
  calls return structured errors and avoid parsing command output.
