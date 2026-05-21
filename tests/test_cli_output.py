"""Tests for optimization CLI output serialization."""

from optimization.cli import _serialize_case_for_output
from testcase_agent.parser.html_parser import GeneratedCase, Step
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
