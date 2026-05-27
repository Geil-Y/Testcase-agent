# ADR-0002: Usage-data-driven CLAUDE.md discipline sections

**Status:** accepted
**Date:** 2026-05-22

## Context

After 94 analyzed Claude Code sessions over one month, the usage data revealed
four recurring friction patterns: buggy code from missed integration wiring (37
instances), misunderstood requests (33), wrong approaches (29), and Claude
overstepping explicit scope boundaries like "analysis-only" or "prompt-only"
(25). Each pattern caused 2-5 avoidable review rounds per change.

## Decision

Add four discipline sections to CLAUDE.md, each directly targeting a specific
friction signal from the data:

1. **Testing Discipline** — targets the #1 buggy-code pattern by requiring full
   test runs and end-to-end call-chain tracing before declaring work complete.
2. **Scope Discipline** — targets the 25 rejected-action incidents by
   prohibiting file edits when the user explicitly limits scope to analysis.
3. **Prompt-Only vs Code Changes** — targets the recurring violation where
   code-layer enforcement was added despite user requiring prompt-only fixes.
4. **Before Proposing a Solution** — targets the 29 wrong-approach incidents by
   requiring problem validation before jumping to solution design.

## Consequences

- Claude is gated by explicit behavioral rules rather than relying on
  conversation-level instructions that degrade over long sessions.
- The "Testing Discipline" section introduces a mandatory wiring-trace step
  that adds upfront cost per change, trading a few minutes for fewer review
  rounds.
- These rules may need tuning as the project evolves — the friction data that
  justified them is a snapshot of sessions from April-May 2026.
