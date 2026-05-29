from testcase_agent.parser.json_parser import MissingInfoItem, TestBasis
from testcase_agent.pipeline.generate import (
    RequirementInput,
    regenerate_case,
    run_pipeline,
)


class CapturingProvider:
    provider_name = "capture"
    model_name = "capture"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        idx = len(self.calls)

        if idx == 1:
            # LLM-A: JSON test basis
            return """{
                "requirement_key": "REQ-BMS-OVP-001",
                "allowed_signals": ["BMS_CellOV_Detect"],
                "allowed_thresholds": ["r_CellOV_Threshold"],
                "allowed_timing": [],
                "allowed_states": [],
                "allowed_observations": [],
                "missing_info": [
                    {"category": "timing", "description": "response timing not specified"}
                ]
            }"""
        elif idx == 2:
            # LLM-B: JSON case intents
            return """{
                "requirement_key": "REQ-BMS-OVP-001",
                "case_intents": [
                    {
                        "intent_id": "intent-1",
                        "coverage_dimension": "normal_behavior",
                        "intent_text": "Verify raw overvoltage detection."
                    },
                    {
                        "intent_id": "intent-2",
                        "coverage_dimension": "boundary_or_threshold",
                        "intent_text": "Verify boundary just-below threshold does not trigger."
                    }
                ]
            }"""
        else:
            # LLM-C: HTML test case
            return """<testcase>
<title>Raw overvoltage detection</title>
<objective>Verify raw overvoltage detection.</objective>
<related_requirement>REQ-BMS-OVP-001</related_requirement>
<precondition>BMS initialized, all parameters within normal operating range, no active faults.</precondition>
<steps>
<step order="1"><action>Set cell voltage above r_CellOV_Threshold</action><expected>Cell voltage is above threshold</expected></step>
<step order="2"><action>Wait response timing [NEEDS REVIEW]</action><expected>BMS_CellOV_Detect := 1</expected></step>
</steps>
<postcondition>System returned to normal operating state.</postcondition>
</testcase>"""


def test_run_pipeline_three_calls():
    provider = CapturingProvider()
    req = RequirementInput(
        requirement_key="REQ-BMS-OVP-001",
        description=(
            "BMS_CellOV_Detect shall be set to 1 when any cell voltage "
            ">= r_CellOV_Threshold."
        ),
    )

    result = run_pipeline(req, provider)

    assert result.error == ""
    # 1 (LLM-A) + 1 (LLM-B) + 2 (LLM-C per intent) = 4
    assert len(provider.calls) == 4
    assert result.test_basis is not None
    assert result.test_basis.requirement_key == "REQ-BMS-OVP-001"
    assert len(result.test_basis.allowed_signals) == 1
    assert len(result.test_basis.missing_info) == 1
    assert result.intent_plan is not None
    assert len(result.intent_plan.case_intents) == 2
    assert len(result.cases) == 2
    assert result.cases[0].title == "Raw overvoltage detection"
    assert len(result.cases[0].steps) == 2


def test_run_pipeline_does_not_send_supplementary_info():
    provider = CapturingProvider()
    req = RequirementInput(
        requirement_key="REQ-BMS-OVP-001",
        description=(
            "BMS_CellOV_Detect shall be set to 1 when any cell voltage "
            ">= r_CellOV_Threshold."
        ),
        supplementary_info="SUPP_ONLY_TOKEN BMS_CellOV_L3_Flag t_CellOV_Debounce",
    )

    run_pipeline(req, provider)

    # 1 + 1 + 2 = 4 calls
    for _, user_prompt in provider.calls:
        assert "SUPP_ONLY_TOKEN" not in user_prompt


def test_run_pipeline_llm_a_prompt_has_only_requirement_fields():
    provider = CapturingProvider()
    req = RequirementInput(
        requirement_key="REQ-BMS-OVP-001",
        description=(
            "BMS_CellOV_Detect shall be set to 1 when any cell voltage "
            ">= r_CellOV_Threshold."
        ),
        function_name="unused_fn",
        supplementary_info="SUPP_ONLY_TOKEN",
    )

    run_pipeline(req, provider)

    _, usr_a = provider.calls[0]
    assert "REQ-BMS-OVP-001" in usr_a
    assert "unused_fn" not in usr_a
    assert "SUPP_ONLY_TOKEN" not in usr_a


def test_run_pipeline_llm_c_prompt_no_review_metadata():
    provider = CapturingProvider()
    req = RequirementInput(
        requirement_key="REQ-BMS-OVP-001",
        description="BMS_CellOV_Detect shall be set to 1 when any cell voltage >= r_CellOV_Threshold.",
    )

    run_pipeline(req, provider)

    _, usr_c = provider.calls[2]
    assert "fact" not in usr_c.lower()
    assert "confidence" not in usr_c.lower()
    assert "routing" not in usr_c.lower()
    assert "reason_code" not in usr_c.lower()
    assert "review_decision" not in usr_c.lower()
    assert "review_memory" not in usr_c.lower()


def test_run_pipeline_parses_json_fenced_output():
    class FencedProvider:
        provider_name = "fenced"
        model_name = "fenced"

        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            self.calls.append((system_prompt, user_prompt))
            idx = len(self.calls)

            if idx == 1:
                return """```json
                {
                    "requirement_key": "REQ-001",
                    "allowed_signals": ["SIG1"],
                    "allowed_thresholds": [],
                    "allowed_timing": [],
                    "allowed_states": [],
                    "allowed_observations": [],
                    "missing_info": []
                }
                ```"""
            elif idx == 2:
                return """```json
                {
                    "requirement_key": "REQ-001",
                    "case_intents": [
                        {
                            "intent_id": "intent-1",
                            "coverage_dimension": "normal_behavior",
                            "intent_text": "Verify basic operation."
                        }
                    ]
                }
                ```"""
            else:
                return """<testcase>
                <title>Basic operation</title>
                <objective>Verify basic operation.</objective>
                <precondition>BMS initialized.</precondition>
                <steps><step order="1"><action>Do thing</action><expected>Works</expected></step></steps>
                <postcondition>System normal.</postcondition>
                </testcase>"""

    provider = FencedProvider()
    req = RequirementInput(requirement_key="REQ-001", description="Test req.")

    result = run_pipeline(req, provider)

    assert result.error == ""
    assert result.test_basis.allowed_signals == ["SIG1"]
    assert len(result.intent_plan.case_intents) == 1
    assert len(result.cases) == 1


def test_run_pipeline_llm_a_parse_failure_sets_error():
    class BadProvider:
        provider_name = "bad"
        model_name = "bad"

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            return "not valid json {{{"

    req = RequirementInput(requirement_key="REQ-001", description="Test req.")
    result = run_pipeline(req, BadProvider())
    assert result.error != ""
    assert "LLM-A" in result.error


def test_run_pipeline_llm_b_parse_failure_sets_error():
    class BadBProvider:
        provider_name = "bad_b"
        model_name = "bad_b"

        def __init__(self) -> None:
            self.call_count = 0

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            self.call_count += 1
            if self.call_count == 1:
                return """{
                    "requirement_key": "REQ-001",
                    "allowed_signals": [],
                    "allowed_thresholds": [],
                    "allowed_timing": [],
                    "allowed_states": [],
                    "allowed_observations": [],
                    "missing_info": []
                }"""
            return "not valid json {{{"

    req = RequirementInput(requirement_key="REQ-001", description="Test req.")
    result = run_pipeline(req, BadBProvider())
    assert result.error != ""
    assert "LLM-B" in result.error


def test_run_pipeline_empty_intents_sets_error():
    class EmptyBProvider:
        provider_name = "empty_b"
        model_name = "empty_b"

        def __init__(self) -> None:
            self.call_count = 0

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            self.call_count += 1
            if self.call_count == 1:
                return """{
                    "requirement_key": "REQ-001",
                    "allowed_signals": [],
                    "allowed_thresholds": [],
                    "allowed_timing": [],
                    "allowed_states": [],
                    "allowed_observations": [],
                    "missing_info": []
                }"""
            return """{
                "requirement_key": "REQ-001",
                "case_intents": []
            }"""

    req = RequirementInput(requirement_key="REQ-001", description="Test req.")
    result = run_pipeline(req, EmptyBProvider())
    assert result.error == "LLM-B produced no case intents"


def test_regenerate_case_with_test_basis():
    class RegenerateProvider:
        provider_name = "regen"
        model_name = "regen"

        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            self.calls.append((system_prompt, user_prompt))
            return """<testcase>
            <title>Regenerated case</title>
            <objective>Verify regenerated case.</objective>
            <precondition>BMS initialized.</precondition>
            <steps><step order="1"><action>Do thing</action><expected>Works</expected></step></steps>
            <postcondition>System normal.</postcondition>
            </testcase>"""

    provider = RegenerateProvider()
    req = RequirementInput(
        requirement_key="REQ-001",
        description="Test req.",
        supplementary_info="SUPP_ONLY_TOKEN",
    )
    tb = TestBasis(
        requirement_key="REQ-001",
        allowed_signals=["SIG1"],
        allowed_thresholds=["THR1"],
        missing_info=[MissingInfoItem(category="timing", description="timing missing")],
    )

    case = regenerate_case(
        req,
        "Verify test.",
        "normal_behavior",
        "Fix something.",
        provider,
        test_basis=tb,
    )

    assert case.title == "Regenerated case"
    _, usr = provider.calls[0]
    assert "SUPP_ONLY_TOKEN" not in usr


def test_run_pipeline_llm_c_parse_failure_recorded():
    class BadCProvider:
        provider_name = "bad_c"
        model_name = "bad_c"

        def __init__(self) -> None:
            self.call_count = 0

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            self.call_count += 1
            if self.call_count == 1:
                return """{
                    "requirement_key": "REQ-001",
                    "allowed_signals": [],
                    "allowed_thresholds": [],
                    "allowed_timing": [],
                    "allowed_states": [],
                    "allowed_observations": [],
                    "missing_info": []
                }"""
            elif self.call_count == 2:
                return """{
                    "requirement_key": "REQ-001",
                    "case_intents": [
                        {
                            "intent_id": "intent-1",
                            "coverage_dimension": "normal_behavior",
                            "intent_text": "Verify something."
                        },
                        {
                            "intent_id": "intent-2",
                            "coverage_dimension": "fault_or_protection",
                            "intent_text": "Verify fault detection."
                        }
                    ]
                }"""
            elif self.call_count == 3:
                # First LLM-C call: bad HTML (no testcase tag, still parses as empty)
                return "this is not valid html"
            else:
                # Second LLM-C call: good HTML
                return """<testcase>
                <title>Fault detection</title>
                <objective>Verify fault detection.</objective>
                <precondition>BMS initialized.</precondition>
                <steps><step order="1"><action>Do thing</action><expected>Works</expected></step></steps>
                <postcondition>System normal.</postcondition>
                </testcase>"""

    req = RequirementInput(requirement_key="REQ-001", description="Test req.")
    result = run_pipeline(req, BadCProvider())

    assert len(result.cases) == 2
    assert result.cases[1].title == "Fault detection"
