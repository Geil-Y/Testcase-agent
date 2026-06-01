---
name: do-issues
description: Complete a GitHub issue end-to-end — read, implement, commit, update acceptance criteria, comment, and close. Use when user references a GitHub issue by number/URL or says "do this issue" / "complete issue #N".
---

# Do Issues

Complete a GitHub issue from start to finish, including the often-forgotten
closing steps. An issue is only done when GitHub shows it closed with all
acceptance criteria checked.

## Full workflow

### 1. Read the issue

- Fetch the issue from GitHub via `mcp__github__get_issue` (owner, repo, number).
- **Do not rely solely on the user's summary.** Read the actual body for
  acceptance criteria, sequencing requirements, and gotchas.
- Print the acceptance criteria as a checklist so the user sees what will be verified.

### 2. Assess current state

- `git status --short` — note any local changes; don't overwrite them.
- Read relevant architecture docs: `CONTEXT.md`, linked ADRs, plan files.
- Read the code files the issue mentions. Confirm you understand the current
  architecture before changing anything.

### 3. Follow the issue's strategy

- If the issue specifies a **sequencing order** ("do X before Y"), follow it
  exactly.
- If the issue says **"use TDD"**, write failing tests first, run them to
  confirm they fail, then implement.
- If the issue says **"don't touch X"**, leave X alone even if it looks tempting.

### 4. Implement in small commits

- One logical change per commit. Do not batch unrelated changes.
- Use conventional commits: `feat(scope):`, `fix(scope):`, `refactor:`, `test:`, `docs:`.
- After each commit, run the focused test suite to catch regressions early.

### 5. Verify

- Run the full test suite. If anything fails, diagnose and fix before proceeding.
- Run any grep/smoke checks the issue requires (e.g., `rg "stale_import" src/`).
- Confirm the issue's acceptance criteria are all satisfied.

### 6. Close the issue on GitHub

This is the part most agents forget. Do all three:

1. **Update the issue body** — change every `- [ ]` in the acceptance criteria
   to `- [x]` using `mcp__github__update_issue`.
2. **Comment** — post a summary with: commit list, test results, key files
   changed, and any residual references. Use `mcp__github__add_issue_comment`.
3. **Close** — `mcp__github__update_issue` with `state: "closed"`.

## Gotchas

- **"Don't commit unless asked" does NOT override an issue's explicit
  "make small commits" instruction.** Treat the issue's instructions as the
  user's explicit ask.

- **Always update the acceptance criteria.** Even if the user doesn't ask,
  ticking the checkboxes in the issue body signals completion to anyone
  watching the tracker.

- **Comment before closing.** A closed issue with no summary comment is
  indistinguishable from an abandoned one.

- **Read the actual issue, not just the user's copy-paste.**
  Users may summarize, but the issue body has the definitive checklist and
  sequencing constraints.

## GitHub MCP tools

| Tool | Purpose |
|---|---|
| `mcp__github__get_issue` | Fetch issue by number |
| `mcp__github__update_issue` | Edit body (check checkboxes), change state |
| `mcp__github__add_issue_comment` | Post completion summary |

The repo is `Geil-Y/Testcase-agent` unless the issue URL says otherwise.
