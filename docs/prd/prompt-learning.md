# PRD: Prompt Learning

## Problem Statement

Users have manually written and human-reviewed historical Reference Test Cases that encode valuable test-writing style, boundary-value habits, coverage choices, and likely no-test patterns. Today, the system can generate cases through the ABC Pipeline, but it does not provide a focused way to learn candidate LLM-A, LLM-B, and LLM-C prompts from those historical assets.

Users need a simple UI-driven workflow that ingests a Requirement Excel file and a Reference Test Case Excel file, learns from the historical requirement-to-case relationships, and produces a versioned Learned Prompt Set for human review. The workflow must stay separate from Case Generation: its goal is prompt generation, not test case generation or prompt effectiveness evaluation.

## Solution

Add a Prompt Learning page alongside the existing Case Generation page in the shared web app. The page lets users upload a Requirement Excel file and a Reference Test Case Excel file, choose sheets, manually map columns, optionally provide a free-text learning instruction, and run Prompt Learning synchronously with visible stage status.

Prompt Learning reads all selected historical assets by default, tolerates common data issues, records those issues in metadata, and produces one mainstream-style Learned Prompt Set. The generated prompt text is English; the learning rationale may be Chinese. The result is automatically saved as a timestamped versioned folder containing:

- `metadata.json`
- `rationale.md`
- `analyze_test_basis.system.html`
- `analyze_test_basis.user.html`
- `plan_case_intents.system.html`
- `plan_case_intents.user.html`
- `generate_case.system.html`
- `generate_case.user.html`

The UI shows version history and read-only result details. It does not activate the learned prompts, edit them, download them, delete versions, run the ABC Pipeline, or evaluate prompt effectiveness.

## User Stories

1. As a test engineer, I want to open one web app with Case Generation and Prompt Learning navigation options, so that I can access both workflows from one place.
2. As a test engineer, I want Case Generation to remain separate from Prompt Learning, so that prompt learning does not accidentally run testcase generation.
3. As a test engineer, I want to upload a Requirement Excel file, so that Prompt Learning can read the source requirements.
4. As a test engineer, I want to select the Requirement sheet, so that files with cover or notes sheets can still be used.
5. As a test engineer, I want to upload a Reference Test Case Excel file, so that Prompt Learning can learn from reviewed historical cases.
6. As a test engineer, I want to select which Reference Test Case sheets to include, so that irrelevant sheets can be excluded while all sheets remain selected by default.
7. As a test engineer, I want to manually map Requirement columns, so that the system does not rely on fragile column-name guessing.
8. As a test engineer, I want to manually map Reference Test Case columns, so that varied historical Excel formats can be used.
9. As a test engineer, I want the UI to remember my most recent column mapping locally, so that repeated runs are faster.
10. As a test engineer, I want to map requirement id and description columns, so that each Requirement can be identified and understood.
11. As a test engineer, I want optional Requirement fields such as function name, requirement type, and supplementary columns to be available, so that useful context is not lost.
12. As a test engineer, I want to map linked requirement ids from one Reference Test Case column, so that multi-requirement historical links can be learned.
13. As a test engineer, I want link parsing to tolerate newline, comma, semicolon, and Chinese punctuation separators, so that manually maintained Excel cells do not need heavy cleanup.
14. As a test engineer, I want to map Reference Test Case title, action, and expected-result columns, so that historical case style can be learned.
15. As a test engineer, I want Reference Test Case objective to be optional, so that historical sheets without objective still work.
16. As a test engineer, I want action and expected-result raw cell text preserved, so that inconsistent step separators do not destroy historical style.
17. As a test engineer, I want action and expected result not to require one-to-one alignment, so that realistic historical cases can be used.
18. As a test engineer, I want one Reference Test Case linked to multiple Requirements to be treated as multiple Requirement-to-Reference-Test-Case examples, so that the generated prompts remain Requirement-centered.
19. As a test engineer, I want multiple Reference Test Case rows linked to the same Requirement to be accepted, so that one Requirement can teach multiple case examples.
20. As a test engineer, I want Requirements with no linked Reference Test Case to teach likely no-test patterns, so that learned prompts can recognize requirements that probably should not generate cases.
21. As a test engineer, I want heading and info rows without links to contribute to no-test learning, so that non-testable requirement-like rows are represented.
22. As a test engineer, I want explicit links to take precedence over requirement type, so that linked heading or info rows are not incorrectly treated as no-test examples.
23. As a test engineer, I want Reference Test Case rows without linked Requirements but with usable case content to be retained as style-only examples, so that LLM-C can still learn writing style.
24. As a test engineer, I want rows missing action or expected-result content to be excluded, so that unusable case rows do not degrade learning.
25. As a test engineer, I want unknown Requirement links to be ignored and reported, so that legacy or dirty data does not fail the whole run.
26. As a test engineer, I want duplicate Requirement ids and duplicate case ids recorded as data issues, so that source data problems are visible.
27. As a test engineer, I want an optional free-text learning instruction, so that I can guide the emphasis of a specific Prompt Learning run.
28. As a test engineer, I want Prompt Learning to run synchronously with visible stage status, so that I know what the system is doing without managing a background job.
29. As a test engineer, I want stage status rather than fake percentage progress, so that progress feedback stays honest.
30. As a test engineer, I want successful runs to automatically save a versioned Learned Prompt Set, so that candidate prompts are preserved for review.
31. As a test engineer, I want failed runs to show clear error information, so that I know whether the issue is Excel parsing, mapping, provider failure, validation, or file save failure.
32. As a test engineer, I want failed runs excluded from the official version list, so that the history contains only complete Learned Prompt Sets.
33. As a test engineer, I want generated prompts validated against the fixed Prompt Learning Framework, so that candidate prompts can later replace same-named ABC prompt files without pipeline code changes.
34. As a test engineer, I want the Learned Prompt Set to use current ABC prompt filenames, so that the relationship to LLM-A, LLM-B, and LLM-C is obvious.
35. As a test engineer, I want learned prompts to preserve required template variables and avoid unknown variables, so that future rendering does not fail.
36. As a test engineer, I want `rationale.md` to open by default after a successful run, so that I first see what the system learned and what conflicts it noticed.
37. As a test engineer, I want prompt files grouped by LLM-A, LLM-B, and LLM-C in the UI, so that review follows the ABC Pipeline stages.
38. As a test engineer, I want prompt content shown read-only, so that Prompt Learning does not become a prompt editor in the first version.
39. As a test engineer, I want a concise parsed-input summary, so that I know how many requirements, cases, links, no-test candidates, and data issues were involved.
40. As a test engineer, I want data issue details expandable in the UI, so that I can locate source Excel problems when needed without cluttering the main page.
41. As a test engineer, I want version history to show version, creation time, requirement count, reference case count, data issue count, and model, so that I can compare prompt learning runs at a glance.
42. As a test engineer, I want Prompt Learning to use the existing LLM Provider abstraction, so that provider configuration remains consistent with the rest of the app.
43. As a test engineer, I do not want to choose the model in the UI for the first version, so that the workflow stays simple.
44. As a reviewer, I want metadata to record the provider/model and free-text instruction, so that I can understand how a Learned Prompt Set was produced.
45. As a reviewer, I want metadata to summarize inputs rather than embed original Excel files, so that version folders stay lightweight and historical assets are not duplicated.
46. As a maintainer, I want uploaded Excel files treated as temporary run inputs, so that official Learned Prompt Set folders contain only prompt learning outputs.
47. As a maintainer, I want Prompt Learning not to create Pipeline Runs, so that it does not pollute Case Generation state.
48. As a maintainer, I want Prompt Learning not to run prompt effectiveness evaluation, so that evaluation remains a separate workflow.

## Implementation Decisions

- Add Prompt Learning as a page option in the shared web app navigation alongside Case Generation.
- Keep Prompt Learning independent from ABC Pipeline execution state. It must not reuse Run, Stage Advance, review state, evaluation state, or pipeline status.
- Add backend Prompt Learning endpoints under a separate route area from existing Case Generation run endpoints.
- Use the existing LLM Provider abstraction for Prompt Learning. The UI does not expose provider/model selection in the first version.
- Use two uploaded Excel files as the input: one Requirement Excel and one Reference Test Case Excel.
- Let the user select one Requirement sheet and one or more Reference Test Case sheets. All Reference Test Case sheets are selected by default.
- Require explicit manual column mapping. Do not infer mappings automatically.
- Store the latest column mapping in browser localStorage for the first version.
- Treat Requirement rows missing requirement key or description as excluded data issues.
- Treat duplicate Requirement keys as data issues; keep the first valid row and ignore later duplicates.
- Treat each Reference Test Case Excel row as one Reference Test Case.
- Expect case ids to uniquely identify Reference Test Cases across selected case sheets. Duplicate case ids are data issues but do not fail learning.
- Allow missing case id and missing title rows to participate when action and expected-result content are usable; record data issues.
- Exclude Reference Test Case rows missing action or expected-result content.
- Preserve raw action and expected-result cell text as the primary learning input.
- Do not require one-to-one action and expected-result alignment.
- Parse linked Requirement identifiers from one mapped Reference Test Case column and tolerate common separators.
- Treat links to unknown Requirement identifiers as ignored data issues.
- Exclude Reference Test Cases whose links all point to unknown Requirements.
- Keep Reference Test Case rows with no links but usable content as style-only examples for LLM-C case-writing style.
- Treat Requirements with no linked Reference Test Case as likely No-Test Requirements for learning no-test patterns.
- Treat unlinked heading/info rows as no-test learning examples, while explicit links take precedence over requirement type.
- Produce exactly one mainstream-style Learned Prompt Set per run. If historical styles conflict, note the conflicts in the learning rationale.
- Allow Prompt Learning to use an internal multi-step learning process. Do not expose internal subtasks as separate user workflows.
- Fix the Prompt Learning Framework in code. The LLM fills prompt content but does not decide file structure, template variables, stage schemas, or required output formats.
- Follow active ABC prompt variable names and output formats so a reviewed Learned Prompt Set can later replace same-named production prompt files without pipeline code changes.
- Generate complete `.html` prompt text, not diffs.
- Validate generated prompt files against the Prompt Learning Framework before official save.
- Write the official Learned Prompt Set only after validation succeeds. Failed attempts do not appear in the official version list.
- Use timestamped version names, with a short suffix if needed to avoid collisions.
- Automatically save successful Learned Prompt Sets to the learned prompts directory.
- Include metadata with parsed-input summary counts, data issue details, provider/model, optional learning instruction, and creation time.
- Include enough data issue location detail for users to find Excel source rows.
- Keep `rationale.md` concise, with mainstream style, coverage and boundary tendencies, no-test patterns, notable conflicts, and data issue summary.
- Write learned prompt text in English. The learning rationale may be Chinese.
- Display Learned Prompt Set contents read-only in the first UI version.
- Do not provide prompt activation, editing, deletion, zip download, copy-to-clipboard, cancellation, or advanced cleanup features in the first version.

## Testing Decisions

- Tests should prioritize external behavior and stable contracts over internal LLM-learning implementation details.
- Prompt Learning API integration tests should use FastAPI `TestClient`, uploaded Excel fixtures, manual mappings, and a mock LLM Provider. They should assert successful creation of a complete Learned Prompt Set, metadata/rationale presence, version listing, and read APIs.
- API integration tests should use a temporary learned-prompts root so tests never pollute real learned prompt assets.
- API integration tests should assert atomic save behavior: failed runs must not enter the official version list and must not leave a formal half-created version folder.
- API integration tests should assert that Prompt Learning does not create Pipeline Runs, test cases, evaluation results, or other ABC Pipeline side effects.
- API integration tests should assert metadata records the provider/model and parsed-input summary.
- Parser/service unit tests should cover Requirement sheet selection, Reference Test Case multi-sheet selection, manual mapped columns, link delimiter tolerance, unknown Requirement links, duplicate Requirement keys, duplicate case ids, missing case id, missing title, missing action or expected result, no-test inference, and style-only Reference Test Cases.
- Parser/service unit tests should cover hard failures: unreadable Excel, missing selected sheet, missing mapped column, no valid Requirements, and no learnable Reference Test Cases.
- Prompt Learning Framework validation tests should cover the exact six prompt filenames, required template variables, unknown template variables, LLM-A and LLM-B JSON output requirements, and LLM-C `<testcase>` HTML output requirements.
- Framework validation tests should assert invalid generated prompt content rejects official save and surfaces a clear error.
- Frontend page tests should cover the shared navigation labels `Case Generation` and `Prompt Learning`.
- Frontend page tests should cover upload controls, sheet selection, manual column mapping, localStorage restoration of the most recent mapping, optional learning instruction, synchronous stage status display, success result display, failure error display, history list, parsed-input summary, expandable data issues, and read-only rationale/prompt viewing.
- Frontend tests should assert prompt files are grouped by LLM-A, LLM-B, and LLM-C with system/user panels.
- Existing test patterns to follow include backend API tests using mock providers and React page/component tests using the current frontend testing setup.
- Learned prompt quality is not tested in this PRD. Running the ABC Pipeline with the generated prompts is explicitly out of scope.

## Out of Scope

- Running the ABC Pipeline with Learned Prompt Set outputs.
- Evaluating whether learned prompts improve generated testcase quality.
- Automatically activating or replacing production prompts.
- Editing Learned Prompt Set contents in the UI.
- Deleting Learned Prompt Set versions in the UI.
- Downloading Learned Prompt Sets as zip files.
- Copy-to-clipboard controls for prompt text.
- Canceling in-progress Prompt Learning runs.
- Background job queues or true percentage progress.
- Advanced corpus management, clustering, prompt comparison, or prompt publishing workflows.
- Provider/model selection in the Prompt Learning UI.
- Storing original uploaded Excel files inside official Learned Prompt Set folders.
- Preflight-only validation workflows before a run.

## Further Notes

- This PRD intentionally keeps the first version small. Prompt Learning should generate candidate prompt assets and make them easy to review, without becoming a full prompt management platform.
- The historical ADRs mention earlier local 7B/8B model assumptions. Current domain context has moved to newer LLM Provider models, but the ABC stage separation and prompt-first architecture remain relevant.
- Prompt Learning may read active production prompts as compatibility references, but historical Reference Test Cases are the source of learned style and coverage habits.
- Source-data imperfections are expected. The product should continue when possible, record data issues clearly, and reserve hard failure for cases where no valid learning run can be produced.
