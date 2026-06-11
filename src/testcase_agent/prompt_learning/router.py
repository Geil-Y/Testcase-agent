"""Prompt Learning API routes."""

from __future__ import annotations

import io
import json

from fastapi import APIRouter, Form, HTTPException, UploadFile
from openpyxl import load_workbook

from .contracts import (
    WorkbookInspection,
    WorkbookSheet,
    RequirementColMap,
    RefTestCaseColMap,
    DataIssue,
    ParsedSummary,
)
from .parse_requirements import parse_requirements
from .parse_ref_cases import parse_ref_test_cases
from .resolve_links import resolve_links

pl_router = APIRouter(prefix="/pl")


def _inspect_workbook(file: UploadFile) -> WorkbookInspection:
    """Read an uploaded .xlsx file and return sheet names and column headers."""
    try:
        contents = file.file.read()
        wb = load_workbook(io.BytesIO(contents), read_only=True)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot read workbook '{file.filename}': {e}",
        ) from e
    finally:
        file.file.seek(0)

    sheets: list[WorkbookSheet] = []
    for name in wb.sheetnames:
        ws = wb[name]
        headers: list[str] = []
        try:
            for cell in ws[1]:
                val = cell.value
                headers.append(str(val).strip() if val is not None else "")
        except IndexError:
            # Sheet has no rows (empty)
            pass
        sheets.append(WorkbookSheet(name=name, columns=headers))
    wb.close()
    return WorkbookInspection(filename=file.filename or "", sheets=sheets)


@pl_router.post("/inspect-workbooks")
def inspect_workbooks(
    req_file: UploadFile,
    case_file: UploadFile,
):
    """Inspect one Requirement workbook and one Reference Test Case workbook.

    Returns sheet names and column headers for both files.
    """
    if not req_file.filename or not req_file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Requirement file must be .xlsx")
    if not case_file.filename or not case_file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Reference Test Case file must be .xlsx")

    req_inspection = _inspect_workbook(req_file)
    case_inspection = _inspect_workbook(case_file)
    return {
        "requirement": req_inspection,
        "referenceTestCase": case_inspection,
    }


@pl_router.post("/parse-and-resolve")
def parse_and_resolve(
    req_file: UploadFile,
    case_file: UploadFile,
    req_sheet: str = Form(...),
    case_sheets: str = Form(...),  # JSON array
    req_mapping: str = Form(...),  # JSON RequirementColMap
    case_mapping: str = Form(...),  # JSON RefTestCaseColMap
):
    """Parse both Excel files, resolve links, and return summary + data issues.

    Accepts multipart form data with two files and four JSON strings
    for sheet selection and column mapping.
    """
    # Validate files
    if not req_file.filename or not req_file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Requirement file must be .xlsx")
    if not case_file.filename or not case_file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="Reference Test Case file must be .xlsx")

    # Parse JSON parameters
    try:
        case_sheet_list: list[str] = json.loads(case_sheets)
        req_map_raw = json.loads(req_mapping)
        case_map_raw = json.loads(case_mapping)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON parameter: {e}")

    req_map = RequirementColMap(
        requirement_key=req_map_raw.get("requirementKey", ""),
        description=req_map_raw.get("description", ""),
        function_name=req_map_raw.get("functionName"),
        requirement_type=req_map_raw.get("requirementType"),
    )
    case_map = RefTestCaseColMap(
        case_id=case_map_raw.get("caseId"),
        linked_requirements=case_map_raw.get("linkedRequirements", ""),
        title=case_map_raw.get("title", ""),
        action=case_map_raw.get("action", ""),
        expected_result=case_map_raw.get("expectedResult", ""),
        objective=case_map_raw.get("objective"),
    )

    # Read file bytes
    req_contents = req_file.file.read()
    case_contents = case_file.file.read()
    req_file.file.seek(0)
    case_file.file.seek(0)

    # Parse
    try:
        parsed_reqs, req_issues = parse_requirements(req_contents, req_sheet, req_map)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    parsed_cases, case_issues = parse_ref_test_cases(case_contents, case_sheet_list, case_map)

    # Resolve
    resolved_links, style_only, no_test, link_issues, summary = resolve_links(
        parsed_reqs, parsed_cases,
    )

    # Merge all data issues
    all_issues: list[DataIssue] = req_issues + case_issues + link_issues
    summary.data_issues = all_issues
    summary.data_issue_count = len(all_issues)

    return {
        "summary": {
            "requirementCount": summary.requirement_count,
            "refTestCaseCount": summary.ref_test_case_count,
            "validLinkCount": summary.valid_link_count,
            "noTestRequirementCount": summary.no_test_requirement_count,
            "styleOnlyCaseCount": summary.style_only_case_count,
            "dataIssueCount": summary.data_issue_count,
        },
        "dataIssues": [{
            "fileType": i.file_type,
            "sheet": i.sheet,
            "row": i.row,
            "issueType": i.issue_type,
            "message": i.message,
        } for i in all_issues],
        "resolvedLinkCount": summary.valid_link_count,
        "styleOnlyCaseCount": len(style_only),
        "noTestRequirementCount": len(no_test),
    }
