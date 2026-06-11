"""Shape and consistency tests for Prompt Learning contracts.

These tests verify that the Python dataclasses in
src/testcase_agent/prompt_learning/contracts.py instantiate correctly with
defaults and that the LEARNED_PROMPT_FILES constant matches expectations.
"""

import pytest
from testcase_agent.prompt_learning.contracts import (
    LEARNED_PROMPT_FILES,
    WorkbookSheet,
    WorkbookInspection,
    RequirementColMap,
    RefTestCaseColMap,
    ColumnMappings,
    DataIssue,
    ParsedRequirement,
    ParsedRefTestCase,
    ResolvedLink,
    StyleOnlyCase,
    NoTestRequirement,
    ParsedSummary,
    LearnedPromptSetMeta,
    LearnedPromptFile,
    LearnedPromptStageGroup,
    LearnedPromptSetVersion,
    FrameworkValidationError,
    FrameworkValidationResult,
)


class TestLearnedPromptFiles:
    def test_exactly_six_files(self):
        assert len(LEARNED_PROMPT_FILES) == 6

    def test_three_unique_stages(self):
        stages = {f.split(".")[0] for f in LEARNED_PROMPT_FILES}
        assert stages == {"analyze_test_basis", "plan_case_intents", "generate_case"}

    def test_every_stage_has_system_and_user(self):
        for stage in ("analyze_test_basis", "plan_case_intents", "generate_case"):
            assert f"{stage}.system.html" in LEARNED_PROMPT_FILES
            assert f"{stage}.user.html" in LEARNED_PROMPT_FILES

    def test_all_end_with_html(self):
        for f in LEARNED_PROMPT_FILES:
            assert f.endswith(".html")


class TestWorkbookInspection:
    def test_basic_inspection(self):
        sheet = WorkbookSheet(name="Sheet1", columns=["A", "B", "C"])
        inspection = WorkbookInspection(
            filename="requirements.xlsx", sheets=[sheet]
        )
        assert inspection.filename == "requirements.xlsx"
        assert len(inspection.sheets) == 1
        assert inspection.sheets[0].columns == ["A", "B", "C"]


class TestColumnMappings:
    def test_full_mappings(self):
        mappings = ColumnMappings(
            requirement=RequirementColMap(
                requirement_key="Req_ID",
                description="Description",
                function_name="Func",
            ),
            ref_test_case=RefTestCaseColMap(
                case_id="Case_ID",
                linked_requirements="Req_ID",
                title="Title",
                action="Action",
                expected_result="Expected",
                objective="Obj",
            ),
            ref_test_case_sheets=["Sheet1"],
        )
        assert mappings.requirement.requirement_key == "Req_ID"
        assert mappings.ref_test_case_sheets == ["Sheet1"]

    def test_minimal_mappings(self):
        mappings = ColumnMappings(
            requirement=RequirementColMap(
                requirement_key="ID",
                description="Desc",
            ),
            ref_test_case=RefTestCaseColMap(
                linked_requirements="Req_ID",
                title="Title",
                action="Steps",
                expected_result="Expected",
            ),
            ref_test_case_sheets=["S1", "S2"],
        )
        assert mappings.requirement.function_name is None
        assert mappings.ref_test_case.case_id is None


class TestDataIssue:
    def test_row_specific_issue(self):
        issue = DataIssue(
            file_type="requirement",
            sheet="Sheet1",
            row=5,
            issue_type="missing_required_field",
            message="Missing requirement key at row 5",
        )
        assert issue.row == 5

    def test_non_row_issue(self):
        issue = DataIssue(
            file_type="reference_test_case",
            sheet="Cases",
            row=None,
            issue_type="empty_sheet",
            message="Sheet has no usable rows",
        )
        assert issue.row is None


class TestParsedRequirement:
    def test_defaults(self):
        req = ParsedRequirement(
            requirement_key="REQ-001",
            description="Cell overvoltage protection",
        )
        assert req.function_name == ""
        assert req.requirement_type == "requirement"
        assert req.supplementary_info == {}
        assert req.source_row == 0

    def test_with_supplementary(self):
        req = ParsedRequirement(
            requirement_key="REQ-001",
            description="Cell overvoltage protection",
            function_name="OVP",
            requirement_type="requirement",
            supplementary_info={"extra_col": "value"},
            source_row=3,
        )
        assert req.supplementary_info["extra_col"] == "value"


class TestParsedRefTestCase:
    def test_basic(self):
        rtc = ParsedRefTestCase(
            case_id="TC-001",
            case_id_generated=False,
            linked_requirements_raw="REQ-001\nREQ-002",
            linked_requirement_keys=["REQ-001", "REQ-002"],
            title="Verify overvoltage cutoff",
            title_missing=False,
            objective="Ensure safety",
            action="1. Set voltage\n2. Measure output",
            expected_result="Output shuts off within 100ms",
            source_sheet="Cases",
            source_row=5,
        )
        assert len(rtc.linked_requirement_keys) == 2

    def test_auto_generated_case_id(self):
        rtc = ParsedRefTestCase(
            case_id="Cases!A7",
            case_id_generated=True,
            linked_requirements_raw="",
            linked_requirement_keys=[],
            title="",
            title_missing=True,
            action="Test action",
            expected_result="Test expected",
            source_sheet="Cases",
            source_row=7,
        )
        assert rtc.case_id_generated is True
        assert rtc.title_missing is True


class TestResolvedLink:
    def test_resolved_and_unresolved(self):
        resolved = ResolvedLink(
            requirement_key="REQ-001",
            ref_case_id="TC-001",
            resolved=True,
        )
        unresolved = ResolvedLink(
            requirement_key="REQ-UNKNOWN",
            ref_case_id="TC-002",
            resolved=False,
        )
        assert resolved.resolved is True
        assert unresolved.resolved is False


class TestStyleOnlyCase:
    def test_basic(self):
        sc = StyleOnlyCase(
            case_id="TC-003",
            title="Style example",
            source_sheet="Cases",
            source_row=10,
        )
        assert sc.title == "Style example"


class TestNoTestRequirement:
    def test_basic(self):
        nt = NoTestRequirement(
            requirement_key="REQ-050",
            description="No historical test for this",
        )
        assert nt.requirement_key == "REQ-050"


class TestParsedSummary:
    def test_defaults(self):
        summary = ParsedSummary()
        assert summary.requirement_count == 0
        assert summary.data_issues == []

    def test_complete_summary(self):
        summary = ParsedSummary(
            requirement_count=100,
            ref_test_case_count=200,
            valid_link_count=350,
            no_test_requirement_count=15,
            style_only_case_count=5,
            data_issue_count=8,
            data_issues=[
                DataIssue(
                    file_type="requirement",
                    sheet="S1",
                    row=3,
                    issue_type="missing_key",
                    message="...",
                ),
            ],
        )
        assert summary.valid_link_count == 350
        assert len(summary.data_issues) == 1


class TestLearnedPromptSetMeta:
    def test_with_optional_instruction(self):
        meta = LearnedPromptSetMeta(
            version="2026-06-11T143000",
            created_at="2026-06-11T14:30:00Z",
            provider="ollama",
            model="qwen2.5:7b",
            learning_instruction="Focus on boundary value tests",
            summary=ParsedSummary(requirement_count=50),
        )
        assert meta.learning_instruction == "Focus on boundary value tests"

    def test_default_summary(self):
        meta = LearnedPromptSetMeta(
            version="v1",
            created_at="2026-01-01T00:00:00Z",
            provider="ollama",
            model="qwen2.5:7b",
        )
        assert meta.summary.requirement_count == 0


class TestLearnedPromptSetVersion:
    def test_full_version(self):
        version = LearnedPromptSetVersion(
            meta=LearnedPromptSetMeta(
                version="2026-06-11T143000",
                created_at="2026-06-11T14:30:00Z",
                provider="ollama",
                model="qwen2.5:7b",
                summary=ParsedSummary(requirement_count=1),
            ),
            rationale="# Learning Rationale\n\n...",
            prompt_groups=[
                LearnedPromptStageGroup(
                    stage="A",
                    stage_label="Analyze Test Basis",
                    system_prompt=LearnedPromptFile(
                        filename="analyze_test_basis.system.html",
                        content="<p>sys</p>",
                    ),
                    user_prompt=LearnedPromptFile(
                        filename="analyze_test_basis.user.html",
                        content="<p>usr</p>",
                    ),
                ),
            ],
        )
        assert len(version.prompt_groups) == 1
        assert version.prompt_groups[0].stage == "A"


class TestFrameworkValidation:
    def test_valid(self):
        result = FrameworkValidationResult(valid=True, errors=[])
        assert result.valid is True

    def test_invalid(self):
        result = FrameworkValidationResult(
            valid=False,
            errors=[
                FrameworkValidationError(
                    filename="generate_case.system.html",
                    message="Missing template variable",
                ),
            ],
        )
        assert len(result.errors) == 1
