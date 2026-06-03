# ADR-0006: SQLite-backed Pipeline Console

**Status:** Accepted

## Context

The ABC pipeline (ADR-0005) stores LLM artifacts as JSON files in timestamped
run directories under `reviews/` or `optimization_runs/`. This works for CLI
batch evaluation but creates friction for the new Pipeline Console web UI:
searching, filtering, and cross-referencing across requirements and runs
requires traversing the filesystem.

The Pipeline Console needs to list hundreds or thousands of imported
requirements with instant search and filter; track multiple runs per
requirement; and support per-item review editing of LLM-A test basis sections.

## Decision

Use a single **SQLite database** (`pipeline_console.db`) at the project root
as the source of truth for the Pipeline Console. The database stores
requirements, runs, run status, all LLM-A/B/C artifacts (test basis sections
and items, case intents, test cases with steps), review decisions, and
evaluation results.

The CLI batch workflow (`run_eval_batch.py`) continues to produce JSON file
artifacts for its own evaluation purposes. The Console database is a separate
data path; it does not replace the CLI's file output.

LLM artifacts that were previously only in JSON files now have normalized
relational schemas (sections → items, intents, cases → steps), enabling
direct SQL queries for the Console API.

## Consequences

- The Console API reads and writes exclusively through the database; no JSON
  file I/O in the API layer.
- Requirements imported from Excel are persisted in the database and survive
  server restarts.
- Run history (1:N per requirement) is naturally queryable by requirement key.
- Review decisions (item-level edits) are stored in-place on the test basis
  items table; no separate review_state.json needed.
- The CLI batch path is unaffected; it continues to use its own file-based
  artifact output.

## Considered Options

- **JSON files + DB index only:** rejected because managing two storage layers
  adds sync complexity and makes item-level editing cumbersome.
- **Keep JSON files only with in-memory search:** rejected because requirements
  scale to thousands of rows and search performance matters.
