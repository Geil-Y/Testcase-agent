from testcase_agent.parser.html_parser import (
    GeneratedCase,
    parse_analysis,
    parse_generated_case,
)


class TestParseAnalysis:
    def test_extracts_all_sections(self):
        html = """<analysis>
        <section name="extracted_signals"><item>Cell Voltage</item></section>
        <section name="extracted_thresholds"><item>OV=4.25V</item></section>
        <section name="extracted_timing"><item>100ms</item></section>
        <section name="extracted_direction">Charge</section>
        <section name="missing_critical_info"><item>BMS model</item></section>
        </analysis>
        <coverage_plan>
        <case_intent coverage="overvoltage">Verify OV protection</case_intent>
        </coverage_plan>"""

        result = parse_analysis(html)

        assert result.signals == ["Cell Voltage"]
        assert result.thresholds == ["OV=4.25V"]
        assert result.timing == ["100ms"]
        assert result.direction == "Charge"
        assert result.missing_critical_info == ["BMS model"]
        assert len(result.case_intents) == 1
        assert result.case_intents[0].coverage == "overvoltage"

    def test_missing_sections_return_defaults(self):
        html = "<analysis></analysis>"

        result = parse_analysis(html)

        assert result.signals == []
        assert result.thresholds == []
        assert result.timing == []
        assert result.direction == ""
        assert result.missing_critical_info == []
        assert result.case_intents == []

    def test_filters_none_found_line_items(self):
        html = """<analysis>
        <section name="extracted_signals">None Found</section>
        </analysis>"""

        result = parse_analysis(html)

        assert result.signals == []

    def test_no_analysis_tag_returns_defaults(self):
        result = parse_analysis("<html></html>")
        assert result.signals == []
        assert result.case_intents == []


class TestParseGeneratedCase:
    def test_parses_full_case(self):
        html = """<testcase>
        <title>TC-001</title>
        <objective>Verify OV protection triggers</objective>
        <precondition>BMS powered, CAN connected</precondition>
        <postcondition>Contactor opens</postcondition>
        <related_requirement>REQ-001</related_requirement>
        <steps>
        <step order="1"><action>Set voltage to 4.25V</action><expected>No alarm</expected></step>
        <step order="2"><action>Raise to 4.35V</action><expected>OV flag set</expected></step>
        </steps>
        </testcase>"""

        result = parse_generated_case(html)

        assert result.title == "TC-001"
        assert result.objective == "Verify OV protection triggers"
        assert result.precondition == "BMS powered, CAN connected"
        assert result.postcondition == "Contactor opens"
        assert result.related_requirement == "REQ-001"
        assert len(result.steps) == 2
        assert result.steps[0].order == 1
        assert result.steps[0].action == "Set voltage to 4.25V"
        assert result.steps[0].expected == "No alarm"
        assert result.steps[1].order == 2
        assert result.steps[1].action == "Raise to 4.35V"
        assert result.steps[1].expected == "OV flag set"

    def test_expected_null_becomes_none(self):
        html = """<testcase>
        <title>T</title>
        <objective>O</objective>
        <precondition>P</precondition>
        <postcondition>P</postcondition>
        <steps><step order="1"><action>Do thing</action><expected>null</expected></step></steps>
        </testcase>"""

        result = parse_generated_case(html)
        assert result.steps[0].expected is None

    def test_missing_testcase_tag_returns_empty(self):
        result = parse_generated_case("<html></html>")
        assert result.title == ""
        assert result.steps == []
