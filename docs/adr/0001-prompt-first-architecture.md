# ADR-0001: Prompt-first architecture

**Status:** superseded by ADR-0003
**Date:** 2026-05-18

## Supersession

ADR-0003 replaces the original two-call HTML generation pipeline with the
clarification-first review pipeline:

```text
decompose_requirement -> clarification review -> plan_case_intents -> intent review -> write_case -> evaluate
```

The core boundary remains valid: code owns plumbing, prompts own generation
philosophy. The obsolete details in this ADR are the old
`analyze_and_plan -> generate_case` workflow and HTML-as-source output format.
The current source of truth is JSON artifacts with code-generated HTML review
views.

## Context

Building a testcase generation agent driven by a local 7B-8B model. The
predecessor project (BMS_HIL_Agent_CodeX) proved that complex multi-layer
prompts degrade small-model output quality — the same model produced better
results in a bare Ollama session than through the full pipeline.

We need the generated case quality to be good on the first pass, while
preserving the ability to swap to larger models later by adjusting prompts
rather than code.

## Decision

**Code owns plumbing; prompts own philosophy.** The codebase provides:

1. Pipeline orchestration (linear function chain, no heavyweight state machine)
2. Provider abstraction (OpenAI-compatible SDK calls Ollama or any future
   endpoint)
3. Deterministic quality gate (schema validation + safety floor)
4. I/O (Excel import, HTML output parsing, web UI)

Prompts — stored as standalone files — own coverage dimension heuristics,
case-writing style, expected depth, and domain knowledge.

**LLM calls are single-task.** LLM#1 analyzes the requirement and produces a
coverage plan. LLM#2 (called N times) generates one case per plan item. No
multi-task mega-prompts.

**Output format is HTML.** HTML tolerates partial parse failures better than
JSON, and small models have more HTML in training data. Schema is defined
alongside each prompt, not in code.

**Quality gate is layered:**
- Development-time: full deterministic checklist for prompt iteration
- Runtime: hard schema validation + safety floor (no real-bench commands)

## Alternatives considered

- **LangGraph state machine (predecessor approach).** Rejected for MVP — a
  linear pipeline with simple while-loop for regenerate covers the needed
  states without the dependency weight.
- **JSON output format.** Rejected — small models have higher parse-failure
  rates with JSON. HTML is more fault-tolerant and equally parsable with
  BeautifulSoup.
- **Keywords-only coverage inference.** Rejected — prompt-driven inference is
  more flexible across model sizes and domain languages. Keywords degenerate
  into a maintenance burden.

## Consequences

- Prompt iteration is the primary tuning mechanism. Prompt files must be
  treated as first-class artifacts with versioning.
- Replacing the LLM model requires prompt review but zero code changes.
- The HTML parser must tolerate structural variations from different models.
- First-pass quality depends almost entirely on prompt quality.
