# Prompt Learning — MVP Usage Guide

Prompt Learning is a feature of the Pipeline Console that learns case-writing
prompt files from historical Requirements and Reference Test Cases. It produces
a **Learned Prompt Set** — versioned candidate prompts that a human can review
and compare before deciding whether to adopt them.

## Navigation

The web app has a left-side navigation with two pages:

- **Case Generation** — the existing test case generation workflow (default).
- **Prompt Learning** — the Prompt Learning workflow.

Click **Prompt Learning** in the left sidebar to begin.

## Input Files

Prompt Learning requires two Excel workbooks:

### Requirement Excel (.xlsx)

Contains the BMS requirements you want to learn from. Each row is one
requirement.

| Required columns | Optional columns |
|---|---|
| Requirement Key | Function Name |
| Description | Requirement Type (requirement / heading / info) |

Any columns not mapped as key/description/function/type are automatically
collected as supplementary information and passed through to the prompts.

### Reference Test Case Excel (.xlsx)

Contains manually-written, human-reviewed historical test cases used as
style and coverage exemplars. Each row is one Reference Test Case.

| Required columns | Optional columns |
|---|---|
| Linked Requirements (may contain multiple keys) | Case ID |
| Title | Objective |
| Action (test steps) | |
| Expected Result | |

The linked-requirements column may use newlines, commas, semicolons, or
Chinese punctuation (，；) as separators when one case covers multiple
requirements.

## Workflow

### 1. Upload Excel Files

Click **Choose File** for each workbook and select your `.xlsx` files. Then
click **Inspect Workbooks** to load the sheet and column structure.

### 2. Select Sheets

- Choose one **Requirement Sheet** from the dropdown.
- Check one or more **Reference Test Case Sheets** (all selected by default).
  Multiple case sheets are assumed to share the same column structure.

### 3. Map Columns

Use the dropdowns to tell Prompt Learning which column in each sheet
corresponds to each expected field. Required fields are marked with `*`.

Your most recent selections and mappings are saved in browser localStorage
and restored when you reopen the page. If a restored mapping references
columns no longer present in the current workbook, those fields are silently
cleared — the page does not crash.

### 4. Parse & Resolve (optional preview)

Click **Parse & Resolve Links** to see a summary of what Prompt Learning
would process: requirement count, reference case count, valid links, No-Test
requirements, style-only cases, and data issues. Data issue details can be
expanded for debugging.

### 5. Run Prompt Learning

Click **Run Prompt Learning** to start the learning process. The run is
**synchronous** — the UI shows the current stage text while waiting. When
complete, the version list refreshes and the new version's `rationale.md`
opens automatically.

On failure, the error message is displayed and no official version is created.

## Output

Successful runs save a versioned **Learned Prompt Set** under:

```
prompts/learned/{version}/
```

Each version folder contains:

| File | Purpose |
|---|---|
| `metadata.json` | Provider, model, input summary counts, data issues |
| `rationale.md` | Learning rationale (summary of style, coverage tendencies, data issues, notable conflicts) |
| `analyze_test_basis.system.html` | LLM-A system prompt (analyze requirement) |
| `analyze_test_basis.user.html` | LLM-A user prompt |
| `plan_case_intents.system.html` | LLM-B system prompt (plan case intents) |
| `plan_case_intents.user.html` | LLM-B user prompt |
| `generate_case.system.html` | LLM-C system prompt (generate test case) |
| `generate_case.user.html` | LLM-C user prompt |

## Version Viewer

The **Learned Prompt Sets** section at the bottom of the page lists all
official versions (newest first). Each version entry shows:

- Version name (timestamp-based)
- Creation date
- LLM model used
- Requirement / Reference Test Case counts
- Data issue count (if any)

Click a version to view its contents:

- **rationale.md** — displayed first by default.
- **Prompt files** — grouped by LLM-A, LLM-B, and LLM-C, with system and
  user prompts shown in read-only panels.

## What Prompt Learning Does NOT Do

This is an MVP. The following are **intentionally out of scope** for the
first version:

- **Activate** a Learned Prompt Set to replace production prompts.
- **Edit** or **delete** learned prompt files through the UI.
- **Download** prompt sets as zip files.
- **Copy** prompt text to clipboard.
- **Cancel** a running Prompt Learning session.
- **Evaluate** learned prompt effectiveness by running the ABC Pipeline.
- **Manage** historical assets beyond one-time upload per run.
- **Export** or **share** Learned Prompt Sets.

Prompt Learning produces candidate prompt files for human review. Comparing
and adopting them into production is a manual, human-driven process.

## Data Quality

Prompt Learning is designed to keep going through imperfect data:

- Rows missing required fields are **excluded** from learning and recorded
  as data issues with sheet and row locations.
- Duplicate Requirement keys keep the **first** valid row.
- Duplicate Case IDs are recorded as data issues but all rows still
  participate in learning.
- Missing Case IDs and titles are recorded as data issues; rows with usable
  action/expected content are still included.

Data issues are visible both in the parse summary (expandable) and in the
`metadata.json` of each Learned Prompt Set version.

## Failure Handling

Prompt Learning treats the following as hard failures (no official version
saved):

- Unreadable Excel files
- Missing selected sheet
- No valid Requirements after parsing
- No learnable Reference Test Cases after parsing
- LLM Provider failure
- Framework validation failure (generated prompts incompatible with ABC Pipeline)
- File save failure

Temp folders from failed runs are automatically cleaned up and never appear
in the official version list.
