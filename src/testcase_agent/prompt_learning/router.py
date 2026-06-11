"""Prompt Learning API routes."""

from __future__ import annotations

import io

from fastapi import APIRouter, HTTPException, UploadFile
from openpyxl import load_workbook

from .contracts import WorkbookInspection, WorkbookSheet

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
