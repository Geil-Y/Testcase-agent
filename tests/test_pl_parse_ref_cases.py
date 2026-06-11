"""Tests for Prompt Learning Reference Test Case Excel parser."""

import io

import pytest
from openpyxl import Workbook

from testcase_agent.prompt_learning.parse_ref_cases import parse_ref_test_cases
from testcase_agent.prompt_learning.contracts import RefTestCaseColMap


def _make_xlsx(sheets: dict[str, list[list[str]]]) -> bytes:
    wb = Workbook()
    for idx, (name, rows) in enumerate(sheets.items()):
        if idx == 0:
            ws = wb.active
            ws.title = name
        else:
            ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestParseRefTestCases:
    def test_parses_valid_rows(self):
        data = _make_xlsx({
            "Cases": [
                ["CID", "Req", "Title", "Action", "Expected", "Obj"],
                ["TC-1", "REQ-1", "Test OV", "Set 4.2V", "Cuts off", "Verify"],
                ["TC-2", "REQ-2", "Test UV", "Set 2.5V", "Restores", ""],
            ],
        })
        mapping = RefTestCaseColMap(
            case_id="CID",
            linked_requirements="Req",
            title="Title",
            action="Action",
            expected_result="Expected",
            objective="Obj",
        )
        cases, issues = parse_ref_test_cases(data, ["Cases"], mapping)
        assert len(cases) == 2
        assert cases[0].case_id == "TC-1"
        assert cases[0].case_id_generated is False
        assert cases[0].title == "Test OV"
        assert cases[0].action == "Set 4.2V"
        assert cases[0].expected_result == "Cuts off"
        assert cases[0].objective == "Verify"
        assert cases[0].linked_requirements_raw == "REQ-1"
        assert cases[0].linked_requirement_keys == []
        assert issues == []

    def test_excludes_missing_action(self):
        data = _make_xlsx({
            "Cases": [
                ["CID", "Req", "Title", "Action", "Expected"],
                ["TC-1", "REQ-1", "Title", "", "Expected"],
                ["TC-2", "REQ-2", "Title", "Action", "Expected"],
            ],
        })
        mapping = RefTestCaseColMap(
            linked_requirements="Req",
            title="Title",
            action="Action",
            expected_result="Expected",
        )
        cases, issues = parse_ref_test_cases(data, ["Cases"], mapping)
        assert len(cases) == 1
        # case_id is auto-generated since no CID column is mapped
        assert cases[0].case_id_generated is True
        assert len(issues) == 2  # missing case_id + missing required field (action)
        assert any(i.issue_type == "missing_required_field" for i in issues)
        assert any(i.issue_type == "missing_case_id" for i in issues)

    def test_excludes_missing_expected(self):
        data = _make_xlsx({
            "Cases": [
                ["CID", "Req", "Title", "Action", "Expected"],
                ["TC-1", "REQ-1", "Title", "Action", ""],
                ["TC-2", "REQ-2", "Title", "Action", "Expected"],
            ],
        })
        mapping = RefTestCaseColMap(
            linked_requirements="Req",
            title="Title",
            action="Action",
            expected_result="Expected",
        )
        cases, issues = parse_ref_test_cases(data, ["Cases"], mapping)
        assert len(cases) == 1
        assert issues[0].row == 2

    def test_missing_case_id_assigns_temporary(self):
        data = _make_xlsx({
            "Cases": [
                ["CID", "Req", "Title", "Action", "Expected"],
                ["", "REQ-1", "Title", "Action", "Expected"],
            ],
        })
        mapping = RefTestCaseColMap(
            case_id="CID",
            linked_requirements="Req",
            title="Title",
            action="Action",
            expected_result="Expected",
        )
        cases, issues = parse_ref_test_cases(data, ["Cases"], mapping)
        assert len(cases) == 1
        assert cases[0].case_id == "Cases!A2"
        assert cases[0].case_id_generated is True
        assert len(issues) == 1
        assert issues[0].issue_type == "missing_case_id"

    def test_missing_title_recorded_as_data_issue(self):
        data = _make_xlsx({
            "Cases": [
                ["CID", "Req", "Title", "Action", "Expected"],
                ["TC-1", "REQ-1", "", "Action", "Expected"],
            ],
        })
        mapping = RefTestCaseColMap(
            case_id="CID",
            linked_requirements="Req",
            title="Title",
            action="Action",
            expected_result="Expected",
        )
        cases, issues = parse_ref_test_cases(data, ["Cases"], mapping)
        assert len(cases) == 1
        assert cases[0].title == ""
        assert cases[0].title_missing is True
        assert len(issues) == 1
        assert issues[0].issue_type == "missing_title"

    def test_duplicate_case_ids_are_data_issues(self):
        data = _make_xlsx({
            "Cases": [
                ["CID", "Req", "Title", "Action", "Expected"],
                ["TC-1", "REQ-1", "First", "Action 1", "Expected 1"],
                ["TC-1", "REQ-2", "Second", "Action 2", "Expected 2"],
            ],
        })
        mapping = RefTestCaseColMap(
            case_id="CID",
            linked_requirements="Req",
            title="Title",
            action="Action",
            expected_result="Expected",
        )
        cases, issues = parse_ref_test_cases(data, ["Cases"], mapping)
        assert len(cases) == 2  # both rows included
        assert any(i.issue_type == "duplicate_case_id" for i in issues)

    def test_multi_sheet_parsing(self):
        data = _make_xlsx({
            "Sheet1": [
                ["CID", "Req", "Title", "Action", "Expected"],
                ["TC-1", "REQ-1", "T1", "A1", "E1"],
            ],
            "Sheet2": [
                ["CID", "Req", "Title", "Action", "Expected"],
                ["TC-2", "REQ-2", "T2", "A2", "E2"],
            ],
        })
        mapping = RefTestCaseColMap(
            case_id="CID",
            linked_requirements="Req",
            title="Title",
            action="Action",
            expected_result="Expected",
        )
        cases, issues = parse_ref_test_cases(data, ["Sheet1", "Sheet2"], mapping)
        assert len(cases) == 2
        assert cases[0].source_sheet == "Sheet1"
        assert cases[1].source_sheet == "Sheet2"

    def test_preserves_raw_action_and_expected_text(self):
        data = _make_xlsx({
            "Cases": [
                ["CID", "Req", "Title", "Action", "Expected"],
                ["TC-1", "REQ-1", "Title", "1. Do X\n2. Do Y", "Result: OK"],
            ],
        })
        mapping = RefTestCaseColMap(
            linked_requirements="Req",
            title="Title",
            action="Action",
            expected_result="Expected",
        )
        cases, issues = parse_ref_test_cases(data, ["Cases"], mapping)
        assert cases[0].action == "1. Do X\n2. Do Y"
        assert cases[0].expected_result == "Result: OK"

    def test_optional_objective_is_preserved_when_present(self):
        data = _make_xlsx({
            "Cases": [
                ["Title", "Action", "Expected", "Obj"],
                ["T", "A", "E", "Objective text"],
            ],
        })
        mapping = RefTestCaseColMap(
            linked_requirements="Req",
            title="Title",
            action="Action",
            expected_result="Expected",
            objective="Obj",
        )
        cases, issues = parse_ref_test_cases(data, ["Cases"], mapping)
        assert cases[0].objective == "Objective text"

    def test_empty_sheet_returns_data_issue(self):
        data = _make_xlsx({"Empty": []})
        mapping = RefTestCaseColMap(
            linked_requirements="Link",
            title="Title",
            action="Action",
            expected_result="Expected",
        )
        cases, issues = parse_ref_test_cases(data, ["Empty"], mapping)
        assert cases == []
        assert len(issues) == 1
        assert issues[0].issue_type == "empty_sheet"

    def test_missing_sheet_returns_data_issue(self):
        data = _make_xlsx({"Other": [["A"]]})
        mapping = RefTestCaseColMap(
            linked_requirements="Link",
            title="Title",
            action="Action",
            expected_result="Expected",
        )
        cases, issues = parse_ref_test_cases(data, ["NonExistent"], mapping)
        assert cases == []
        assert len(issues) == 1
        assert issues[0].issue_type == "missing_sheet"
