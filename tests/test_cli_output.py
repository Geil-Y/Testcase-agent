"""Tests for optimization CLI output serialization."""

from types import SimpleNamespace

from optimization.cli import _build_req_info_for_eval, _serialize_case_for_output
from testcase_agent.parser.html_parser import GeneratedCase, Step
from testcase_agent.pipeline.generate import RequirementInput
from testcase_agent.quality.gate import QualityReport


def _case() -> GeneratedCase:
    return GeneratedCase(
        title="TC-01",
        objective="Verify protection",
        precondition="Ready",
        postcondition="Done",
        related_requirement="REQ-001",
        steps=[Step(order=1, action="Set voltage to [NEEDS REVIEW]", expected="Flag set")],
        raw_html="<testcase></testcase>",
    )


def _quality() -> QualityReport:
    return QualityReport(case_index=0, passed=True, failures=[], warnings=[])


def test_case_output_with_retry_meta():
    data = _serialize_case_for_output(
        _case(),
        _quality(),
        retry_meta={"attempts": 2, "exhausted": True, "failures": [["3.2.1"], ["4.1.4"]], "self_check_changed": True},
        sanitize_enabled=True,
        sanitize_replacements=["4.2V"],
    )

    assert data["retry"] == {
        "attempts": 2,
        "exhausted": True,
        "failures": [["3.2.1"], ["4.1.4"]],
        "self_check_changed": True,
    }
    assert data["sanitize"] == {
        "enabled": True,
        "replacement_count": 1,
        "replacements": ["4.2V"],
    }


def test_case_output_without_retry_meta():
    data = _serialize_case_for_output(
        _case(),
        _quality(),
    )

    assert "retry" not in data
    assert data["sanitize"] == {
        "enabled": False,
        "replacement_count": 0,
        "replacements": [],
    }
    assert data["quality"] == {"passed": True, "failures": [], "warnings": []}


# ── _build_req_info_for_eval ──────────────────────────────────────────────


def _mock_analysis(signals=None, thresholds=None, timing=None, missing_info_items=None):
    """Minimal analysis-like object for _build_req_info_for_eval."""
    return SimpleNamespace(
        signals=signals or [],
        thresholds=thresholds or [],
        timing=timing or [],
        missing_info_items=missing_info_items or [],
    )


def _req():
    return RequirementInput(
        requirement_key="REQ-TEST-001",
        description="Test requirement.",
    )


class TestBuildReqInfoForEval:
    def test_set_meta_empty_list_overrides_analysis_missing(self):
        """When expected_missing_categories=[] in set_meta, use [] even if analysis has missing items."""
        req = _req()
        analysis = _mock_analysis(
            missing_info_items=[
                SimpleNamespace(category="timing"),
                SimpleNamespace(category="state"),
            ],
        )
        set_meta = {"expected_missing_categories": [], "evaluation_bucket": "test"}

        info = _build_req_info_for_eval(req, analysis, set_meta)

        assert info["expected_missing_categories"] == []

    def test_falls_back_to_analysis_when_set_meta_lacks_key(self):
        """When set_meta exists but lacks expected_missing_categories, fallback to analysis."""
        req = _req()
        analysis = _mock_analysis(
            missing_info_items=[
                SimpleNamespace(category="timing"),
                SimpleNamespace(category="state"),
            ],
        )
        set_meta = {"evaluation_bucket": "test"}  # no expected_missing_categories

        info = _build_req_info_for_eval(req, analysis, set_meta)

        assert info["expected_missing_categories"] == ["timing", "state"]

    def test_no_set_meta_falls_back_to_analysis(self):
        """When set_meta is None, fallback to analysis.missing_info_items."""
        req = _req()
        analysis = _mock_analysis(
            missing_info_items=[SimpleNamespace(category="signal")],
        )

        info = _build_req_info_for_eval(req, analysis, None)

        assert info["expected_missing_categories"] == ["signal"]

    def test_no_set_meta_and_no_analysis_returns_empty(self):
        """When both set_meta and analysis are None/empty, return empty list."""
        req = _req()
        info = _build_req_info_for_eval(req, None, None)
        assert info["expected_missing_categories"] == []
