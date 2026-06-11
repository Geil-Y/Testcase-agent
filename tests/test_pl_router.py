"""Tests for Prompt Learning API routes."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from testcase_agent.api import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def _make_xlsx(sheets: dict[str, list[list[str]]]) -> io.BytesIO:
    """Create an in-memory .xlsx workbook from {sheet_name: [[row1_col1, ...], ...]}."""
    wb = Workbook()
    for idx, (name, rows) in enumerate(sheets.items()):
        if idx == 0:
            ws = wb.active
            ws.title = name
        else:
            ws = wb.create_sheet(title=name)
        for row_data in rows:
            ws.append(row_data)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


class TestInspectWorkbooks:
    def test_returns_sheets_and_columns_for_both_files(self, client):
        req_buf = _make_xlsx({
            "Requirements": [
                ["Req ID", "Description", "Func"],
                ["REQ-1", "Overvoltage", "OVP"],
            ],
        })
        case_buf = _make_xlsx({
            "Cases": [
                ["Case ID", "Req Link", "Title", "Action", "Expected"],
                ["TC-1", "REQ-1", "Test OV", "Set 4.2V", "Cuts off"],
            ],
        })

        res = client.post(
            "/api/v1/console/pl/inspect-workbooks",
            files=[
                ("req_file", ("req.xlsx", req_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                ("case_file", ("case.xlsx", case_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ],
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["requirement"]["filename"] == "req.xlsx"
        assert data["referenceTestCase"]["filename"] == "case.xlsx"

        req_sheets = data["requirement"]["sheets"]
        assert len(req_sheets) == 1
        assert req_sheets[0]["name"] == "Requirements"
        assert req_sheets[0]["columns"] == ["Req ID", "Description", "Func"]

        case_sheets = data["referenceTestCase"]["sheets"]
        assert len(case_sheets) == 1
        assert case_sheets[0]["name"] == "Cases"
        assert case_sheets[0]["columns"] == ["Case ID", "Req Link", "Title", "Action", "Expected"]

    def test_handles_multiple_sheets(self, client):
        case_buf = _make_xlsx({
            "Sheet1": [["A", "B"]],
            "Sheet2": [["C", "D"]],
            "Sheet3": [["E", "F"]],
        })
        req_buf = _make_xlsx({"S": [["X"]]})

        res = client.post(
            "/api/v1/console/pl/inspect-workbooks",
            files=[
                ("req_file", ("r.xlsx", req_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                ("case_file", ("c.xlsx", case_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ],
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert len(data["referenceTestCase"]["sheets"]) == 3

    def test_rejects_non_xlsx_requirement_file(self, client):
        case_buf = _make_xlsx({"S": [["A"]]})
        res = client.post(
            "/api/v1/console/pl/inspect-workbooks",
            files=[
                ("req_file", ("req.csv", io.BytesIO(b"a,b"), "text/csv")),
                ("case_file", ("case.xlsx", case_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ],
        )
        assert res.status_code == 422

    def test_rejects_non_xlsx_case_file(self, client):
        req_buf = _make_xlsx({"S": [["A"]]})
        res = client.post(
            "/api/v1/console/pl/inspect-workbooks",
            files=[
                ("req_file", ("req.xlsx", req_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                ("case_file", ("case.csv", io.BytesIO(b"a,b"), "text/csv")),
            ],
        )
        assert res.status_code == 422

    def test_rejects_unreadable_file(self, client):
        case_buf = _make_xlsx({"S": [["A"]]})
        res = client.post(
            "/api/v1/console/pl/inspect-workbooks",
            files=[
                ("req_file", ("req.xlsx", io.BytesIO(b"not an xlsx"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                ("case_file", ("case.xlsx", case_buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ],
        )
        assert res.status_code == 422

    def test_empty_sheet_has_no_columns(self, client):
        """Sheet with no header row returns empty columns list."""
        buf = _make_xlsx({"Empty": []})
        res = client.post(
            "/api/v1/console/pl/inspect-workbooks",
            files=[
                ("req_file", ("r.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                ("case_file", ("c.xlsx", buf, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ],
        )
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["requirement"]["sheets"][0]["columns"] == []
        assert data["referenceTestCase"]["sheets"][0]["columns"] == []

    def test_health_endpoint_still_works(self, client):
        res = client.get("/api/v1/health")
        assert res.status_code == 200
