"""Prompt Learning runner — orchestrate parse → resolve → LLM → validate → save."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..provider.base import LlmProvider
from .contracts import (
    LEARNED_PROMPT_FILES,
    LearnedPromptSetMeta,
    ParsedSummary,
)
from .parse_requirements import parse_requirements, RequirementColMap
from .parse_ref_cases import parse_ref_test_cases, RefTestCaseColMap
from .resolve_links import resolve_links
from .framework_validation import validate_prompt_set
from .file_store import save_learned_prompt_set


@dataclass
class RunResult:
    """Result of a Prompt Learning run."""

    success: bool
    version: str = ""
    meta: Optional[LearnedPromptSetMeta] = None
    error: str = ""


# Regex to extract prompt file content from LLM response
_HTML_FILE_RE = re.compile(
    r'<file\s+name="([^"]+)">\s*((?:(?!</file>).)*)\s*</file>',
    re.DOTALL,
)


def _build_learning_prompt(
    requirements_data: list[dict],
    ref_cases_data: list[dict],
    summary: ParsedSummary,
    learning_instruction: Optional[str],
) -> str:
    """Build the Prompt Learning user prompt from parsed inputs."""

    req_lines = []
    for r in requirements_data:
        req_lines.append(f"- {r['requirementKey']}: {r['description']}")
    cases_lines = []
    for c in ref_cases_data:
        cases_lines.append(f"- {c['caseId']}: {c['title']}")
    no_test_lines = []
    style_only_lines = []

    instruction_text = f"\nLearning instruction: {learning_instruction}" if learning_instruction else ""

    return f"""You are generating improved versions of six prompt files for an ABC Pipeline test case generation system.

Learning input summary:
- {summary.requirement_count} requirements
- {summary.ref_test_case_count} reference test cases
- {summary.valid_link_count} valid Requirement-to-Reference-Test-Case links
- {summary.no_test_requirement_count} requirements with no historical tests (likely No-Test)
- {summary.style_only_case_count} style-only reference cases
- {summary.data_issue_count} data issues encountered

Requirements:
{chr(10).join(req_lines[:100])}

Reference Test Cases:
{chr(10).join(cases_lines[:100])}
{instruction_text}

## Output format

Respond with exactly six <file> blocks, one for each prompt file:

<file name="analyze_test_basis.system.html">
... system prompt for LLM-A: analyze test basis ...
</file>
<file name="analyze_test_basis.user.html">
... user prompt for LLM-A ...
</file>
<file name="plan_case_intents.system.html">
... system prompt for LLM-B: plan case intents ...
</file>
<file name="plan_case_intents.user.html">
... user prompt for LLM-B ...
</file>
<file name="generate_case.system.html">
... system prompt for LLM-C: generate case ...
</file>
<file name="generate_case.user.html">
... user prompt for LLM-C ...
</file>

## Guidelines

- Each system prompt must use Jinja2 template variables matching the ABC Pipeline contract.
- LLM-A (analyze_test_basis): requires {{requirement_key}}, {{description}}. Output JSON.
- LLM-B (plan_case_intents): requires {{requirement_key}}, {{description}}, {{allowed_signals}}, {{allowed_thresholds}}, {{allowed_timing}}, {{allowed_states}}, {{allowed_observations}}, {{missing_info}}. Output JSON.
- LLM-C (generate_case): requires {{requirement_key}}, {{description}}, {{supplementary_info}}, {{coverage_dimension}}, {{case_intent}}, {{review_comment}}, {{extracted_signals}}, {{extracted_thresholds}}, {{extracted_timing}}, {{extracted_states}}, {{extracted_observations}}, {{missing_info}}, {{missing_info_items}}. Output <testcase> HTML.
- Adapt prompt writing style, coverage habits, and boundary-value tendencies from the reference test cases.
- Note that unlinked requirements are likely No-Test examples — the LLM-A prompt should learn to identify these.
- Preserve the stage boundary: each stage does one thing.
"""


def _parse_llm_response(response: str) -> dict[str, str]:
    """Extract <file name="...">content</file> blocks from the LLM response."""
    files: dict[str, str] = {}
    for match in _HTML_FILE_RE.finditer(response):
        name = match.group(1)
        content = match.group(2).strip()
        files[name] = content
    return files


def run_prompt_learning(
    req_bytes: bytes,
    case_bytes: bytes,
    req_sheet: str,
    case_sheets: list[str],
    req_mapping: RequirementColMap,
    case_mapping: RefTestCaseColMap,
    provider: LlmProvider,
    *,
    learning_instruction: Optional[str] = None,
) -> RunResult:
    """Run the full Prompt Learning pipeline.

    Parse → Resolve → Build prompt → LLM → Validate → Save.
    Returns RunResult with version on success.
    """
    # 1. Parse
    try:
        parsed_reqs, req_issues = parse_requirements(req_bytes, req_sheet, req_mapping)
    except (ValueError, Exception) as e:
        return RunResult(success=False, error=f"Requirement parse error: {e}")

    try:
        parsed_cases, case_issues = parse_ref_test_cases(case_bytes, case_sheets, case_mapping)
    except Exception as e:
        return RunResult(success=False, error=f"Reference Test Case parse error: {e}")

    # 2. Resolve
    resolved_links, style_only, no_test, link_issues, summary = resolve_links(
        parsed_reqs, parsed_cases,
    )
    all_issues = req_issues + case_issues + link_issues
    summary.data_issues = all_issues
    summary.data_issue_count = len(all_issues)

    # 3. Pre-flight checks
    if summary.requirement_count == 0:
        return RunResult(success=False, error="No valid Requirements found after parsing")
    if summary.ref_test_case_count == 0:
        return RunResult(success=False, error="No learnable Reference Test Cases found after parsing")

    # 4. Build learning prompt and call LLM
    req_data = [
        {
            "requirementKey": r.requirement_key,
            "description": r.description,
            "requirementType": r.requirement_type,
        }
        for r in parsed_reqs
    ]
    case_data = [
        {
            "caseId": c.case_id,
            "title": c.title,
            "action": c.action[:200],
            "expectedResult": c.expected_result[:200],
        }
        for c in parsed_cases
    ]

    user_prompt = _build_learning_prompt(req_data, case_data, summary, learning_instruction)
    system_prompt = (
        "You are a prompt engineering assistant. Generate improved ABC Pipeline prompt files "
        "learned from historical test case data. Respond with exactly six <file> blocks."
    )

    try:
        llm_response = provider.complete(system_prompt, user_prompt)
    except Exception as e:
        return RunResult(success=False, error=f"LLM Provider error: {e}")

    # 5. Parse LLM response
    prompt_files = _parse_llm_response(llm_response)
    if len(prompt_files) != 6:
        missing = set(LEARNED_PROMPT_FILES) - set(prompt_files.keys())
        return RunResult(
            success=False,
            error=f"LLM response incomplete: missing {sorted(missing) if missing else 'unknown files'}",
        )

    # 6. Validate
    validation = validate_prompt_set(prompt_files)
    if not validation.valid:
        error_msgs = "; ".join(e.message for e in validation.errors[:5])
        return RunResult(success=False, error=f"Framework validation failed: {error_msgs}")

    # 7. Build metadata and save
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = LearnedPromptSetMeta(
        version="",
        created_at=now,
        provider=provider.provider_name,
        model=provider.model_name,
        learning_instruction=learning_instruction,
        summary=summary,
    )

    # Build rationale from prompt file headers (first 200 chars of each)
    rationale_parts = [
        "# Learning Rationale",
        "",
        f"Provider: {provider.provider_name}",
        f"Model: {provider.model_name}",
        f"Created: {now}",
        "",
        f"## Input summary",
        f"- Requirements: {summary.requirement_count}",
        f"- Reference Test Cases: {summary.ref_test_case_count}",
        f"- Valid Links: {summary.valid_link_count}",
        f"- No-Test Requirements: {summary.no_test_requirement_count}",
        f"- Style-Only Cases: {summary.style_only_case_count}",
        f"- Data Issues: {summary.data_issue_count}",
        "",
    ]
    if learning_instruction:
        rationale_parts.append(f"## Learning Instruction\n{learning_instruction}\n")
    if all_issues:
        rationale_parts.append("## Data Issues")
        for issue in all_issues:
            rationale_parts.append(f"- [{issue.issue_type}] {issue.file_type}/{issue.sheet}"
                                   f"{f' row {issue.row}' if issue.row else ''}: {issue.message}")

    rationale = "\n".join(rationale_parts)

    try:
        version = save_learned_prompt_set(meta, rationale, prompt_files)
    except Exception as e:
        return RunResult(success=False, error=f"File save error: {e}")

    meta.version = version
    return RunResult(success=True, version=version, meta=meta)
