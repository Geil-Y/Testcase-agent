# PRD: Pipeline Console MVP

## Problem Statement

Reviewing the clarification-first test case generation pipeline is currently too
inconvenient. The phase 1 pipeline produces JSON artifacts and static HTML
reports, but the reviewer still has to move between files, manually edit
structured review decisions, remember which stage can run next, and avoid
accidentally using stale downstream artifacts after changing upstream review
decisions.

The project needs a local product-grade **Pipeline Console** that makes the
existing review pipeline usable as the main workflow without weakening the core
architecture: JSON artifacts remain the source of truth, humans remain
responsible for review decisions, and the pipeline stages remain the execution
core.

## Solution

Build a local **Pipeline Console** as the phase 2 user entry point. The Console
imports Requirements, shows the latest import batch, lets the reviewer select
one Requirement, creates one **Active Run** for that Requirement, hosts the
**Review Workbench** for **Clarification Review** and **Case Intent Review**,
advances validated pipeline stages, and shows generated cases and evaluation
results.

The MVP is single-user and local. It supports many imported Requirements, but
only one Active Run is advanced at a time. It does not become a batch queue,
multi-user workflow system, model configuration UI, or prompt optimization
console.

The Console replaces the old sandbox-era API and UI surface rather than living
beside it. New user-facing work targets the Pipeline Console only.

## User Stories

1. As a reviewer, I want to open a local Pipeline Console, so that I can review generated artifacts without editing JSON files by hand.
2. As a reviewer, I want to upload an Excel file and map its columns, so that structured Requirements can be imported into the Console.
3. As a reviewer, I want confirmed imports to persist, so that refreshing the browser does not lose the imported Requirement list.
4. As a reviewer, I want the Console home page to open my latest import batch by default, so that I can resume where I left off.
5. As a reviewer, I want to choose from recent import batches, so that I can return to earlier Requirement sets.
6. As a reviewer, I want a Requirements table with key, description, function, type, latest run status, latest run time, and actions, so that I can choose what to review next.
7. As a reviewer, I want to expand a Requirement row, so that I can inspect the full description and supplementary info before starting a run.
8. As a reviewer, I want to see whether a Requirement already has a historical run, so that I can continue existing work instead of accidentally creating duplicates.
9. As a reviewer, I want to open the latest run for a Requirement, so that I can continue the current review path.
10. As a reviewer, I want to start a new run for a Requirement, so that I can intentionally re-run the pipeline from the beginning.
11. As a reviewer, I want run names to include a timestamp, Requirement key, and description slug, so that run folders are recognizable without relying on anonymous sequence numbers.
12. As a reviewer, I want Start Run to immediately prepare Clarification Review, so that I do not have to create an empty run and then perform a separate first-stage action.
13. As a reviewer, I want the run workspace to show the current Requirement and Active Run, so that I always know what I am reviewing.
14. As a reviewer, I want a fixed stage navigation for the Active Run, so that I can see whether the run is at Clarification Review, Case Intent Review, generated cases, evaluation, or blocked state.
15. As a reviewer, I want run status to be inferred from artifacts, so that the Console stays compatible with CLI-created artifacts and does not require a separate run database.
16. As a reviewer, I want to edit Clarification Review decisions in a form, so that I can approve, clarify, mark missing information, edit, or block ambiguity items safely.
17. As a reviewer, I want Save Draft on Clarification Review, so that I can save incomplete work without passing validation.
18. As a reviewer, I want Save & Prepare Case Intent Review, so that the Console saves my Clarification Review, validates it, creates the Clarified Test Basis, and prepares Case Intent Review in one explicit action.
19. As a reviewer, I want block decisions in Clarification Review to stop the run, so that unsafe Requirements do not proceed to case intent planning.
20. As a reviewer, I want validation errors to point to exact fields and rows, so that I can fix incomplete decisions quickly.
21. As a reviewer, I want controlled reason code selection, so that review decisions use the canonical registry rather than arbitrary text.
22. As a reviewer, I want reason text to remain free-form, so that I can explain context-specific decisions.
23. As a reviewer, I want an Accept All Recommendations action, so that I can bulk-fill low-risk recommended decisions without automatically advancing the pipeline.
24. As a reviewer, I want orange/red routed items to require confirmation before bulk acceptance, so that high-risk review items are not accepted accidentally.
25. As a reviewer, I want filtering by decision status, routing, coverage dimension where applicable, and text search, so that large reviews are manageable.
26. As a reviewer, I want pending and high-risk items sorted first, so that I do not miss unresolved review work.
27. As a reviewer, I want Review Memory hints shown inline as advisory context, so that prior human decisions can inform but not control my review.
28. As a reviewer, I want Review Memory hints to never auto-select decisions or generate content, so that Review Memory remains advisory rather than authoritative.
29. As a reviewer, I want to edit Case Intent Review decisions in a form, so that I can approve, reject, revise, merge, split, or defer proposed case intents.
30. As a reviewer, I want Save Draft on Case Intent Review, so that I can save incomplete intent review work.
31. As a reviewer, I want Save & Generate Cases, so that the Console saves my Case Intent Review, validates it, writes the Approved Case Plan, generates test cases, evaluates them, and opens Results.
32. As a reviewer, I want rejected and deferred intents excluded from generated cases, so that only approved/revised/split-child intents are written as cases.
33. As a reviewer, I want revised intents to be used for case writing, so that human intent corrections drive generation.
34. As a reviewer, I want merged intents to generate only from the surviving target intent, so that duplicate case behavior is avoided.
35. As a reviewer, I want split children to generate multiple cases, so that one broad intent can become several focused cases.
36. As a reviewer, I want Results to be read-only in the MVP, so that generated cases do not drift away from the approved plan and traceability.
37. As a reviewer, I want to return to upstream review decisions and regenerate downstream artifacts, so that corrections happen at the right source of truth.
38. As a reviewer, I want downstream artifacts archived when upstream normalized content changes, so that stale Case Intent Reviews, Approved Case Plans, generated cases, and evaluations are not treated as active.
39. As a reviewer, I want unchanged upstream content to open existing downstream artifacts instead of rerunning LLM stages, so that accidental clicks do not waste time or overwrite review work.
40. As a reviewer, I want explicit Regenerate actions, so that I can intentionally archive active downstream artifacts and rerun a stage.
41. As a reviewer, I want Regenerate actions to require confirmation and list affected artifacts, so that I understand what will be archived.
42. As a reviewer, I want long-running LLM actions to run as jobs, so that the UI can show running, failed, or done state instead of blocking indefinitely.
43. As a reviewer, I want only one running job at a time, so that review artifacts are not modified concurrently.
44. As a reviewer, I want editing locked while a job is running, so that a stage function does not read partially changed review data.
45. As a reviewer, I want job failures to be visible and retryable, so that local LLM or validation failures can be handled without losing artifacts.
46. As a reviewer, I want Real LLM mode to be the default, so that production review work is not accidentally performed with mock outputs.
47. As a developer, I want Mock Mode available only through explicit developer configuration and visibly labeled, so that Console flows can be tested without confusing reviewers.
48. As a reviewer, I want to manually import Review Memory after a completed run, so that only intentional reviewed decisions become historical support.
49. As a reviewer, I want Review Memory import to never happen automatically, so that drafts and mistaken decisions do not pollute memory.
50. As a reviewer, I want to download key artifacts and export an active run bundle, so that reviewed outputs can be shared or archived.
51. As a reviewer, I want archived artifacts excluded from the default bundle unless selected, so that the active result is clear.
52. As an engineer, I want the Console API to call pipeline stage functions directly, so that API behavior uses structured errors and shared pipeline core rather than parsing CLI output.
53. As an engineer, I want the CLI to remain a script adapter over the same pipeline core, so that command-line and Console usage stay behaviorally aligned.
54. As an engineer, I want Console code treated as product code, so that it is tested and maintained rather than becoming an untracked prototype.
55. As an engineer, I want the old sandbox UI and API surface removed rather than maintained in parallel, so that the codebase has one current user path.

## Implementation Decisions

- Use the glossary terms **Pipeline Console**, **Review Workbench**, and **Active Run** consistently.
- The Pipeline Console is the phase 2 user entry point for the clarification-first review pipeline.
- The Review Workbench is the review module within the Pipeline Console and initially covers Clarification Review and Case Intent Review.
- The MVP supports many imported Requirements but advances one selected Active Run at a time.
- One selected Requirement creates one Active Run; batch execution is out of scope for the MVP.
- Run state remains artifact-driven. The Console derives state from active artifacts and validation outcomes rather than introducing a separate run database.
- New run names use a timestamp plus Requirement key and description slug.
- Existing old-style run folders remain readable, but new Console and CLI runs should use the timestamped human-readable naming convention.
- Historical runs are matched to Requirements by reading the run's input artifact. Directory names are labels, not the source of truth.
- The Console home page owns import, recent imports, Requirements listing, and Start/Open Run actions.
- The run workspace owns fixed stage navigation, Review Workbench pages, Results, job state, and run-level actions.
- The Requirements list is not shown inside the run workspace sidebar.
- Confirmed Excel imports persist as JSON import batches under the reviews area.
- The home page opens the latest import batch by default and provides a recent import selector.
- Start Run writes a single-Requirement run input artifact, calls the clarification preparation stage, and opens Clarification Review.
- The Console API invokes review pipeline stage functions directly. It does not shell out to CLI commands.
- The CLI remains available for scripts and should share the same pipeline core behavior.
- Console endpoints use a dedicated Console API namespace under the existing API version prefix.
- The old sandbox-era API and UI are removed rather than retained beside the Console.
- The frontend is a static local UI using HTML, CSS, and vanilla JavaScript; no React/Vue build chain is introduced for the MVP.
- Long-running stage actions use a local in-memory job model with polling.
- The MVP allows only one running job at a time and locks editing plus stage actions while a job is running.
- Save Draft persists incomplete review decisions and does not require formal validation.
- Save & Prepare Case Intent Review saves Clarification Review, validates it, writes the Clarified Test Basis, and prepares Case Intent Review if not blocked.
- Save & Generate Cases saves Case Intent Review, validates it, writes the Approved Case Plan, generates cases, evaluates them, and opens Results.
- Clarification Review block decisions stop the Active Run before Case Intent Review.
- Case Intent Review approve/reject/revise/merge/split/defer decisions map to the existing Approved Case Plan semantics.
- Results are read-only in the MVP. Corrections happen by revising upstream review decisions and regenerating downstream artifacts.
- Normalized content hashes determine whether upstream review changes invalidate downstream artifacts.
- Changed upstream content archives downstream artifacts before regeneration.
- Unchanged upstream content opens existing downstream artifacts rather than rerunning LLM stages.
- Explicit Regenerate actions archive current downstream artifacts and rerun the relevant stage after confirmation.
- Reason codes use controlled selection from the registry, filtered by review type and decision.
- Reason text remains free-form for contextual explanation.
- Review Memory hints are displayed inline as advisory context only and never auto-select decisions or generate review content.
- Review Memory import remains explicit and is never automatic.
- Real LLM mode is the default; Mock Mode is developer-configured and visibly labeled.
- Results support downloading key artifacts and exporting the active run bundle, with archived artifacts optional.
- The MVP does not provide Open Run Folder or Copy Run Path actions.

## Testing Decisions

- Console tests should focus on external behavior and API contracts, not internal implementation details of existing pipeline stages.
- Existing review pipeline tests remain the source of truth for stage behavior.
- Test import preview and confirm behavior, including persisted import batches and recent import selection.
- Test run naming and slug generation, including collision handling.
- Test historical run matching by input artifact rather than directory name.
- Test run status inference from active artifacts, including blocked Clarification Review and evaluated runs.
- Test Start Run creates a single-Requirement Active Run and starts Clarification Review preparation.
- Test Save Draft persists incomplete review decisions without requiring validation.
- Test Save & Prepare Case Intent Review succeeds when validation passes and stops when validation fails.
- Test block decisions produce blocked state and prevent Case Intent Review preparation.
- Test Save & Generate Cases advances through validation, approved plan creation, case generation, and evaluation when inputs are valid.
- Test validation errors are returned with stage, item, field, and human-readable detail.
- Test normalized content hash comparison for unchanged and changed upstream artifacts.
- Test downstream archive behavior on changed upstream content.
- Test unchanged upstream content reuses existing downstream artifacts.
- Test Regenerate confirmation paths and affected artifact lists.
- Test job creation, polling, success, failure, retryability, and global single-job locking.
- Test editing/stage actions are rejected or disabled while a job is running.
- Test reason code options are constrained by review type and decision.
- Test Review Memory hints remain advisory and do not mutate decisions.
- Test explicit Review Memory import and ensure no automatic memory write occurs during ordinary save or advance actions.
- Test Results export of active artifacts and optional archived artifacts.
- Add lightweight frontend smoke coverage only after enough UI behavior exists to make it valuable; prioritize API and artifact behavior first.

## Out of Scope

- Batch queue execution across many Requirements.
- Multi-user collaboration, permissions, locking, or audit trails.
- Background job persistence across server restarts.
- Celery, Redis, or external queue infrastructure.
- Model/provider configuration UI.
- Prompt optimization UI.
- Embedding search.
- Automatic human review skipping.
- Code-driven automatic approve/reject.
- Direct editing of generated cases in Results.
- A separate Test Case Review artifact.
- Full replacement of existing evaluator logic.
- Open Run Folder or Copy Run Path buttons.
- React/Vue or another frontend build chain.
- Maintaining the old sandbox UI or sandbox-era API routes in parallel.

## Further Notes

This PRD follows ADR-0004. The guiding constraint is that the Pipeline Console
improves review ergonomics without changing the pipeline's trust model: JSON
artifacts remain the source of truth, humans make review decisions, Review
Memory is advisory, and stage functions remain the pipeline execution core.

## Publication Note

Published to GitHub as https://github.com/Geil-Y/Testcase-agent/issues/1 with
the `ready-for-agent` label.
