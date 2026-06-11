"""Prompt Learning Reference Test Case Excel parser."""

from __future__ import annotations

import io

from openpyxl import load_workbook

from .contracts import (
    RefTestCaseColMap,
    ParsedRefTestCase,
    DataIssue,
)


def parse_ref_test_cases(
    file_bytes: bytes,
    sheet_names: list[str],
    mapping: RefTestCaseColMap,
) -> tuple[list[ParsedRefTestCase], list[DataIssue]]:
    """Parse Reference Test Case rows from selected sheets using manual column mapping.

    Returns (parsed_cases, data_issues).
    """
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True)

    all_cases: list[ParsedRefTestCase] = []
    all_issues: list[DataIssue] = []
    seen_case_ids: dict[str, str] = {}  # case_id -> first occurrence sheet+row

    for sheet_name in sheet_names:
        if sheet_name not in wb.sheetnames:
            all_issues.append(DataIssue(
                file_type="reference_test_case",
                sheet=sheet_name,
                row=None,
                issue_type="missing_sheet",
                message=f"Sheet '{sheet_name}' not found in workbook — skipped",
            ))
            continue

        ws = wb[sheet_name]

        # Read header row
        headers: list[str] = []
        try:
            for cell in ws[1]:
                val = cell.value
                headers.append(str(val).strip() if val is not None else "")
        except IndexError:
            all_issues.append(DataIssue(
                file_type="reference_test_case",
                sheet=sheet_name,
                row=None,
                issue_type="empty_sheet",
                message=f"Sheet '{sheet_name}' has no rows",
            ))
            continue

        # Resolve column indices
        case_id_col = _col_index(headers, mapping.case_id) if mapping.case_id else -1
        link_col = _col_index(headers, mapping.linked_requirements)
        title_col = _col_index(headers, mapping.title)
        action_col = _col_index(headers, mapping.action)
        expected_col = _col_index(headers, mapping.expected_result)
        obj_col = _col_index(headers, mapping.objective) if mapping.objective else -1

        rows = list(ws.iter_rows(min_row=2, values_only=True))
        for row_idx, row in enumerate(rows, start=2):
            action = _cell_str(row, action_col)
            expected = _cell_str(row, expected_col)

            # Missing action or expected → exclude + data issue
            if not action or not expected:
                all_issues.append(DataIssue(
                    file_type="reference_test_case",
                    sheet=sheet_name,
                    row=row_idx,
                    issue_type="missing_required_field",
                    message=f"Sheet '{sheet_name}' row {row_idx}: missing {'action' if not action else 'expected result'} — excluded",
                ))
                continue

            case_id = _cell_str(row, case_id_col)
            case_id_generated = False
            if not case_id:
                case_id = f"{sheet_name}!A{row_idx}"
                case_id_generated = True
                all_issues.append(DataIssue(
                    file_type="reference_test_case",
                    sheet=sheet_name,
                    row=row_idx,
                    issue_type="missing_case_id",
                    message=f"Sheet '{sheet_name}' row {row_idx}: missing case id — assigned '{case_id}'",
                ))

            # Duplicate case id → record issue, keep first
            if case_id in seen_case_ids and not case_id_generated:
                all_issues.append(DataIssue(
                    file_type="reference_test_case",
                    sheet=sheet_name,
                    row=row_idx,
                    issue_type="duplicate_case_id",
                    message=f"Sheet '{sheet_name}' row {row_idx}: duplicate case id '{case_id}' (first seen at {seen_case_ids[case_id]})",
                ))
                # Still include the row for learning
            elif not case_id_generated:
                seen_case_ids[case_id] = f"sheet '{sheet_name}' row {row_idx}"

            title = _cell_str(row, title_col)
            title_missing = False
            if not title:
                title_missing = True
                all_issues.append(DataIssue(
                    file_type="reference_test_case",
                    sheet=sheet_name,
                    row=row_idx,
                    issue_type="missing_title",
                    message=f"Sheet '{sheet_name}' row {row_idx}: missing title",
                ))

            linked_raw = _cell_str(row, link_col)
            objective = _cell_str(row, obj_col)

            all_cases.append(ParsedRefTestCase(
                case_id=case_id,
                case_id_generated=case_id_generated,
                linked_requirements_raw=linked_raw,
                linked_requirement_keys=[],  # filled later by resolver
                title=title,
                title_missing=title_missing,
                objective=objective,
                action=action,
                expected_result=expected,
                source_sheet=sheet_name,
                source_row=row_idx,
            ))

    wb.close()
    return all_cases, all_issues


def _col_index(headers: list[str], col_name: str) -> int:
    try:
        return headers.index(col_name)
    except ValueError:
        return -1


def _cell_str(row: tuple, index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    val = row[index]
    return str(val).strip() if val is not None else ""
