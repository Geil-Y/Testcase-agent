from testcase_agent.parser.html_parser import (
    AnalysisResult,
    GeneratedCase,
    MissingInfo,
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
        assert result.states == []
        assert result.observations == []
        assert result.missing_info_items == []

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

    def test_parse_extracted_states(self):
        html = """<analysis>
        <section name="extracted_states">
        <item>NormalMode</item>
        <item>OvervoltageProtection</item>
        </section>
        </analysis>"""

        result = parse_analysis(html)

        assert result.states == ["NormalMode", "OvervoltageProtection"]

    def test_parse_extracted_observations(self):
        html = """<analysis>
        <section name="extracted_observations">
        <item>CAN_OV_Flag status</item>
        <item>Contactor state change</item>
        </section>
        </analysis>"""

        result = parse_analysis(html)

        assert result.observations == ["CAN_OV_Flag status", "Contactor state change"]

    def test_missing_critical_info_old_format(self):
        html = """<analysis>
        <section name="missing_critical_info">
        <item>response timing not specified</item>
        <item>threshold value not provided</item>
        </section>
        </analysis>"""

        result = parse_analysis(html)

        assert result.missing_critical_info == [
            "response timing not specified",
            "threshold value not provided",
        ]
        assert len(result.missing_info_items) == 2
        assert result.missing_info_items[0].category == ""
        assert result.missing_info_items[0].description == "response timing not specified"
        assert result.missing_info_items[1].category == ""
        assert result.missing_info_items[1].description == "threshold value not provided"

    def test_missing_critical_info_new_format_with_category(self):
        html = """<analysis>
        <section name="missing_critical_info">
        <item category="timing">response timing not specified</item>
        <item category="threshold">overvoltage threshold not provided</item>
        </section>
        </analysis>"""

        result = parse_analysis(html)

        assert result.missing_critical_info == [
            "response timing not specified",
            "overvoltage threshold not provided",
        ]
        assert len(result.missing_info_items) == 2
        assert result.missing_info_items[0].category == "timing"
        assert result.missing_info_items[0].description == "response timing not specified"
        assert result.missing_info_items[1].category == "threshold"
        assert result.missing_info_items[1].description == "overvoltage threshold not provided"

    def test_missing_critical_info_mixed_format(self):
        html = """<analysis>
        <section name="missing_critical_info">
        <item category="timing">response timing not specified</item>
        <item>BMS model not given</item>
        <item category="signal">fault signal name not provided</item>
        </section>
        </analysis>"""

        result = parse_analysis(html)

        assert result.missing_critical_info == [
            "response timing not specified",
            "BMS model not given",
            "fault signal name not provided",
        ]
        assert len(result.missing_info_items) == 3
        assert result.missing_info_items[0].category == "timing"
        assert result.missing_info_items[1].category == ""
        assert result.missing_info_items[2].category == "signal"


class TestAnalysisDataSerialization:
    """Verify AnalysisResult → dict serialization matches cli.py format."""

    def _serialize(self, analysis: AnalysisResult) -> dict:
        return {
            "signals": analysis.signals,
            "thresholds": analysis.thresholds,
            "timing": analysis.timing,
            "states": analysis.states,
            "observations": analysis.observations,
            "direction": analysis.direction,
            "missing_critical_info": analysis.missing_critical_info,
            "missing_info_items": [
                {"category": mi.category, "description": mi.description}
                for mi in analysis.missing_info_items
            ],
            "case_intents": [
                {"coverage": ci.coverage, "description": ci.description}
                for ci in analysis.case_intents
            ],
        }

    def test_serializes_new_fields(self):
        analysis = AnalysisResult(
            states=["NormalMode", "FaultMode"],
            observations=["DTC_OV set", "Contactor opened"],
            missing_info_items=[
                MissingInfo(category="timing", description="response time not specified"),
                MissingInfo(category="threshold", description="OV threshold missing"),
            ],
            missing_critical_info=["response time not specified", "OV threshold missing"],
        )
        data = self._serialize(analysis)
        assert data["states"] == ["NormalMode", "FaultMode"]
        assert data["observations"] == ["DTC_OV set", "Contactor opened"]
        assert data["missing_info_items"] == [
            {"category": "timing", "description": "response time not specified"},
            {"category": "threshold", "description": "OV threshold missing"},
        ]
        assert data["missing_critical_info"] == [
            "response time not specified", "OV threshold missing",
        ]

    def test_empty_new_fields_default_to_empty_lists(self):
        analysis = AnalysisResult()
        data = self._serialize(analysis)
        assert data["states"] == []
        assert data["observations"] == []
        assert data["missing_info_items"] == []

    def test_mixed_category_missing_info(self):
        analysis = AnalysisResult(
            missing_info_items=[
                MissingInfo(category="timing", description="timing missing"),
                MissingInfo(category="", description="old-format item"),
                MissingInfo(category="signal", description="signal name missing"),
            ],
            missing_critical_info=[
                "timing missing", "old-format item", "signal name missing",
            ],
        )
        data = self._serialize(analysis)
        assert len(data["missing_info_items"]) == 3
        assert data["missing_info_items"][0] == {
            "category": "timing", "description": "timing missing",
        }
        assert data["missing_info_items"][1] == {
            "category": "", "description": "old-format item",
        }
        assert data["missing_info_items"][2] == {
            "category": "signal", "description": "signal name missing",
        }


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
