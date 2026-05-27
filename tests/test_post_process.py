from testcase_agent.parser.html_parser import GeneratedCase, Step
from testcase_agent.pipeline.post_process import (
    sanitize_numeric_values,
    strip_needless_markers,
)


def _make_case(steps: list[Step] | None = None, raw_html: str = "") -> GeneratedCase:
    return GeneratedCase(
        title="Test",
        objective="Verify something",
        precondition="Ready",
        postcondition="Done",
        steps=steps or [],
        raw_html=raw_html,
    )


class TestStripNeedlessMarkers:
    def test_skips_when_has_missing(self):
        case = _make_case(
            steps=[Step(order=1, action="Set [NEEDS REVIEW] value", expected="OK")],
        )
        result = strip_needless_markers(case, has_missing=True)
        assert result.steps[0].action == "Set [NEEDS REVIEW] value"

    def test_removes_from_action(self):
        case = _make_case(
            steps=[Step(order=1, action="Set [NEEDS REVIEW] voltage to 12V", expected="OK")],
        )
        result = strip_needless_markers(case, has_missing=False)
        assert result.steps[0].action == "Set voltage to 12V"

    def test_removes_from_expected(self):
        case = _make_case(
            steps=[Step(order=1, action="Check", expected="[NEEDS REVIEW] stable")],
        )
        result = strip_needless_markers(case, has_missing=False)
        assert result.steps[0].expected == "stable"

    def test_removes_from_raw_html(self):
        case = _make_case(raw_html="<step>[NEEDS REVIEW] action</step>")
        result = strip_needless_markers(case, has_missing=False)
        assert "[NEEDS REVIEW]" not in result.raw_html

    def test_handles_none_expected(self):
        case = _make_case(
            steps=[Step(order=1, action="Do [NEEDS REVIEW] thing", expected=None)],
        )
        result = strip_needless_markers(case, has_missing=False)
        assert result.steps[0].action == "Do thing"
        assert result.steps[0].expected is None

    def test_no_markers_passes_through(self):
        case = _make_case(
            steps=[Step(order=1, action="Do thing", expected="OK")],
        )
        result = strip_needless_markers(case, has_missing=False)
        assert result.steps[0].action == "Do thing"


class TestSanitizeNumericValues:
    def _kwargs(self, **overrides):
        defaults = {
            "requirement_description": "",
            "supplementary_info": "",
            "extracted_signals": [],
            "extracted_thresholds": [],
            "extracted_timing": [],
        }
        defaults.update(overrides)
        return defaults

    def test_keeps_exact_match(self):
        case = _make_case(
            steps=[Step(order=1, action="Set voltage to 4.25V", expected="OK")],
        )
        result, reps = sanitize_numeric_values(
            case, **self._kwargs(requirement_description="OV threshold is 4.25V")
        )
        assert result.steps[0].action == "Set voltage to 4.25V"
        assert len(reps) == 0

    def test_keeps_boundary_derivation_within_20pct(self):
        case = _make_case(
            steps=[Step(order=1, action="Apply 4.68V to cell", expected="OK")],
        )
        result, reps = sanitize_numeric_values(
            case, **self._kwargs(requirement_description="OV threshold is 4.25V")
        )
        # 4.68 is ~10% above 4.25, should be kept
        assert "4.68V" in result.steps[0].action
        assert len(reps) == 0

    def test_replaces_unrelated_value(self):
        case = _make_case(
            steps=[Step(order=1, action="Apply 9.99V", expected="OK")],
        )
        result, reps = sanitize_numeric_values(
            case, **self._kwargs(requirement_description="OV threshold is 4.25V")
        )
        assert "9.99V" not in result.steps[0].action
        assert "[NEEDS REVIEW]" in result.steps[0].action
        assert len(reps) == 1

    def test_scans_requirement_description(self):
        case = _make_case(
            steps=[Step(order=1, action="Set current to 10A", expected="OK")],
        )
        result, reps = sanitize_numeric_values(
            case, **self._kwargs(requirement_description="The limit is 10A")
        )
        assert "10A" in result.steps[0].action
        assert len(reps) == 0

    def test_replaces_in_expected_field(self):
        case = _make_case(
            steps=[Step(order=1, action="Check", expected="Voltage reads 7.77V")],
        )
        result, reps = sanitize_numeric_values(
            case, **self._kwargs(requirement_description="OV threshold is 4.25V")
        )
        assert "7.77V" not in result.steps[0].expected
        assert len(reps) == 1

    def test_mixed_units_are_distinct(self):
        case = _make_case(
            steps=[Step(order=1, action="Apply 4.25A", expected="OK")],
        )
        result, reps = sanitize_numeric_values(
            case, **self._kwargs(requirement_description="OV threshold is 4.25V")
        )
        # 4.25A is not a match for 4.25V (different unit)
        assert "[NEEDS REVIEW]" in result.steps[0].action
        assert len(reps) == 1

    def test_supplementary_info_does_not_authorize_values(self):
        case = _make_case(
            steps=[Step(order=1, action="Wait 500ms", expected="OK")],
        )
        result, reps = sanitize_numeric_values(
            case,
            **self._kwargs(supplementary_info="Debounce time: 500ms"),
        )
        assert "500ms" not in result.steps[0].action
        assert "[NEEDS REVIEW]" in result.steps[0].action
        assert reps == ["500ms"]

    def test_explicit_accepted_test_basis_authorizes_values(self):
        case = _make_case(
            steps=[Step(order=1, action="Wait 500ms", expected="OK")],
        )
        result, reps = sanitize_numeric_values(
            case,
            **self._kwargs(
                supplementary_info="Debounce time: 500ms",
                accepted_test_basis="For this review, use debounce time 500ms.",
            ),
        )
        assert result.steps[0].action == "Wait 500ms"
        assert reps == []
