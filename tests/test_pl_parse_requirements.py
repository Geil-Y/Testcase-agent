"""Tests for Prompt Learning Requirement Excel parser."""

import io

import pytest
from openpyxl import Workbook

from testcase_agent.prompt_learning.parse_requirements import parse_requirements
from testcase_agent.prompt_learning.contracts import RequirementColMap


def _make_xlsx(rows: list[list[str]], sheet_name: str = "Sheet1") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestParseRequirements:
    def test_parses_valid_rows(self):
        data = _make_xlsx([
            ["Key", "Desc", "Func", "Type"],
            ["REQ-1", "Overvoltage protection", "OVP", "requirement"],
            ["REQ-2", "Undervoltage protection", "UVP", "requirement"],
        ])
        mapping = RequirementColMap(
            requirement_key="Key",
            description="Desc",
            function_name="Func",
            requirement_type="Type",
        )
        reqs, issues = parse_requirements(data, "Sheet1", mapping)
        assert len(reqs) == 2
        assert reqs[0].requirement_key == "REQ-1"
        assert reqs[0].description == "Overvoltage protection"
        assert reqs[0].function_name == "OVP"
        assert reqs[0].requirement_type == "requirement"
        assert reqs[0].source_row == 2
        assert issues == []

    def test_excludes_missing_key(self):
        data = _make_xlsx([
            ["Key", "Desc"],
            ["", "No key row"],
            ["REQ-1", "Valid row"],
        ])
        mapping = RequirementColMap(requirement_key="Key", description="Desc")
        reqs, issues = parse_requirements(data, "Sheet1", mapping)
        assert len(reqs) == 1
        assert reqs[0].requirement_key == "REQ-1"
        assert len(issues) == 1
        assert issues[0].issue_type == "missing_required_field"
        assert issues[0].row == 2

    def test_excludes_missing_description(self):
        data = _make_xlsx([
            ["Key", "Desc"],
            ["REQ-1", ""],
            ["REQ-2", "Has desc"],
        ])
        mapping = RequirementColMap(requirement_key="Key", description="Desc")
        reqs, issues = parse_requirements(data, "Sheet1", mapping)
        assert len(reqs) == 1
        assert reqs[0].requirement_key == "REQ-2"
        assert len(issues) == 1
        assert issues[0].row == 2

    def test_handles_duplicate_keys(self):
        data = _make_xlsx([
            ["Key", "Desc"],
            ["REQ-1", "First occurrence"],
            ["REQ-1", "Duplicate — should be ignored"],
            ["REQ-2", "Another valid"],
        ])
        mapping = RequirementColMap(requirement_key="Key", description="Desc")
        reqs, issues = parse_requirements(data, "Sheet1", mapping)
        assert len(reqs) == 2
        assert reqs[0].description == "First occurrence"
        assert len(issues) == 1
        assert issues[0].issue_type == "duplicate_key"
        assert issues[0].row == 3

    def test_optional_fields_are_preserved(self):
        data = _make_xlsx([
            ["Key", "Desc", "Func", "Type"],
            ["REQ-1", "Test", "", ""],
            ["REQ-2", "Test2", "FUNC", "heading"],
        ])
        mapping = RequirementColMap(
            requirement_key="Key",
            description="Desc",
            function_name="Func",
            requirement_type="Type",
        )
        reqs, issues = parse_requirements(data, "Sheet1", mapping)
        assert reqs[0].function_name == ""
        assert reqs[0].requirement_type == "requirement"  # default
        assert reqs[1].function_name == "FUNC"
        assert reqs[1].requirement_type == "heading"

    def test_supplementary_info_columns(self):
        data = _make_xlsx([
            ["Key", "Desc", "Extra1", "Extra2"],
            ["REQ-1", "Test", "val1", "val2"],
        ])
        mapping = RequirementColMap(requirement_key="Key", description="Desc")
        reqs, issues = parse_requirements(data, "Sheet1", mapping)
        assert len(reqs) == 1
        assert reqs[0].supplementary_info == {"Extra1": "val1", "Extra2": "val2"}

    def test_heading_and_info_rows_are_preserved(self):
        data = _make_xlsx([
            ["Key", "Desc", "Type"],
            ["HD-1", "A heading", "heading"],
            ["INFO-1", "Info row", "info"],
            ["REQ-1", "A real requirement", "requirement"],
        ])
        mapping = RequirementColMap(
            requirement_key="Key",
            description="Desc",
            requirement_type="Type",
        )
        reqs, issues = parse_requirements(data, "Sheet1", mapping)
        assert len(reqs) == 3
        assert reqs[0].requirement_type == "heading"
        assert reqs[1].requirement_type == "info"
        assert reqs[2].requirement_type == "requirement"

    def test_empty_sheet(self):
        data = _make_xlsx([], sheet_name="Empty")
        mapping = RequirementColMap(requirement_key="Key", description="Desc")
        reqs, issues = parse_requirements(data, "Empty", mapping)
        assert reqs == []
        assert len(issues) == 1
        assert issues[0].issue_type == "empty_sheet"

    def test_missing_sheet_raises(self):
        data = _make_xlsx([["A"]])
        mapping = RequirementColMap(requirement_key="A", description="A")
        with pytest.raises(ValueError, match="not found"):
            parse_requirements(data, "NonExistent", mapping)

    def test_missing_mapped_column_is_treated_as_empty(self):
        """When a mapped column doesn't exist in headers, the value is empty string."""
        data = _make_xlsx([
            ["Key", "Desc"],
            ["REQ-1", "Test"],
        ])
        mapping = RequirementColMap(
            requirement_key="Key",
            description="Desc",
            function_name="NonExistent",
        )
        reqs, issues = parse_requirements(data, "Sheet1", mapping)
        assert len(reqs) == 1
        assert reqs[0].function_name == ""
