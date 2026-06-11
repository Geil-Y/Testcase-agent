"""Resolve Requirement-to-Reference-Test-Case links for Prompt Learning."""

from __future__ import annotations

import re

from .contracts import (
    ParsedRequirement,
    ParsedRefTestCase,
    ResolvedLink,
    StyleOnlyCase,
    NoTestRequirement,
    DataIssue,
    ParsedSummary,
)

# Separator pattern: newline, comma, semicolon, Chinese punctuation
_LINK_SEP = re.compile(r"[\n,;；，、]+")


def resolve_links(
    requirements: list[ParsedRequirement],
    ref_cases: list[ParsedRefTestCase],
) -> tuple[
    list[ResolvedLink],
    list[StyleOnlyCase],
    list[NoTestRequirement],
    list[DataIssue],
    ParsedSummary,
]:
    """Resolve all links between parsed Requirements and Reference Test Cases.

    Returns (resolved_links, style_only_cases, no_test_requirements, data_issues, summary).
    """
    req_keys: set[str] = {r.requirement_key for r in requirements}
    issues: list[DataIssue] = []
    resolved_links: list[ResolvedLink] = []
    style_only_cases: list[StyleOnlyCase] = []
    linked_req_keys: set[str] = set()

    for case in ref_cases:
        raw = case.linked_requirements_raw.strip()

        # Parse linked requirement identifiers from the cell
        if raw:
            parsed_keys = _parse_link_keys(raw)
            case.linked_requirement_keys = parsed_keys
        else:
            parsed_keys = []

        if not parsed_keys:
            # No links at all → style-only case (if usable content)
            issues.append(DataIssue(
                file_type="reference_test_case",
                sheet=case.source_sheet,
                row=case.source_row,
                issue_type="missing_links",
                message=(
                    f"Case '{case.case_id}' (sheet '{case.source_sheet}' "
                    f"row {case.source_row}): no linked Requirements — "
                    f"kept as style-only example"
                ),
            ))
            style_only_cases.append(StyleOnlyCase(
                case_id=case.case_id,
                title=case.title,
                source_sheet=case.source_sheet,
                source_row=case.source_row,
            ))
            continue

        # Resolve each key against known Requirements
        all_unknown = True
        for key in parsed_keys:
            if key in req_keys:
                resolved_links.append(ResolvedLink(
                    requirement_key=key,
                    ref_case_id=case.case_id,
                    resolved=True,
                ))
                linked_req_keys.add(key)
                all_unknown = False
            else:
                resolved_links.append(ResolvedLink(
                    requirement_key=key,
                    ref_case_id=case.case_id,
                    resolved=False,
                ))
                issues.append(DataIssue(
                    file_type="reference_test_case",
                    sheet=case.source_sheet,
                    row=case.source_row,
                    issue_type="unknown_requirement_link",
                    message=(
                        f"Case '{case.case_id}' (sheet '{case.source_sheet}' "
                        f"row {case.source_row}): link to unknown "
                        f"Requirement '{key}' — ignored"
                    ),
                ))

        # If all links are unknown → also mark as style-only
        if all_unknown:
            issues.append(DataIssue(
                file_type="reference_test_case",
                sheet=case.source_sheet,
                row=case.source_row,
                issue_type="all_links_unknown",
                message=(
                    f"Case '{case.case_id}' (sheet '{case.source_sheet}' "
                    f"row {case.source_row}): all links point to unknown "
                    f"Requirements — excluded from linked learning"
                ),
            ))
            style_only_cases.append(StyleOnlyCase(
                case_id=case.case_id,
                title=case.title,
                source_sheet=case.source_sheet,
                source_row=case.source_row,
            ))

    # Identify No-Test Requirements (not linked to any Ref Test Case)
    no_test_reqs: list[NoTestRequirement] = []
    for req in requirements:
        if req.requirement_key not in linked_req_keys:
            no_test_reqs.append(NoTestRequirement(
                requirement_key=req.requirement_key,
                description=req.description,
            ))

    # Build summary
    summary = ParsedSummary(
        requirement_count=len(requirements),
        ref_test_case_count=len(ref_cases),
        valid_link_count=sum(1 for l in resolved_links if l.resolved),
        no_test_requirement_count=len(no_test_reqs),
        style_only_case_count=len(style_only_cases),
        data_issue_count=len(issues),
        data_issues=issues,
    )

    return resolved_links, style_only_cases, no_test_reqs, issues, summary


def _parse_link_keys(raw: str) -> list[str]:
    """Parse multiple Requirement identifiers from a cell.

    Supports newline, comma, semicolon, and Chinese punctuation separators.
    """
    parts = _LINK_SEP.split(raw)
    keys: list[str] = []
    for part in parts:
        key = part.strip()
        if key:
            keys.append(key)
    return keys
