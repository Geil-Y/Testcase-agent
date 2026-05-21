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
        if len(self.calls) == 1:
            return """<analysis>
<section name="extracted_signals"><item>BMS_CellOV_Detect</item></section>
<section name="extracted_thresholds"><item>r_CellOV_Threshold</item></section>
<section name="extracted_timing"><item>none found</item></section>
<section name="extracted_states"><item>none found</item></section>
<section name="extracted_observations"><item>none found</item></section>
<section name="extracted_direction">triggering</section>
<section name="missing_critical_info"><item category="timing">response timing not specified</item></section>
</analysis>
<coverage_plan>
<case_intent coverage="normal_behavior">Verify raw overvoltage detection.</case_intent>
</coverage_plan>"""
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


def test_run_pipeline_does_not_send_supplementary_info_to_generation_prompts():
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

    assert len(provider.calls) == 2
    assert all("SUPP_ONLY_TOKEN" not in user for _, user in provider.calls)
    assert all("BMS_CellOV_L3_Flag" not in user for _, user in provider.calls)
    assert all("t_CellOV_Debounce" not in user for _, user in provider.calls)


def test_regenerate_case_does_not_send_supplementary_info_to_prompt():
    provider = CapturingProvider()
    req = RequirementInput(
        requirement_key="REQ-BMS-OVP-001",
        description=(
            "BMS_CellOV_Detect shall be set to 1 when any cell voltage "
            ">= r_CellOV_Threshold."
        ),
        supplementary_info="SUPP_ONLY_TOKEN BMS_CellOV_L3_Flag t_CellOV_Debounce",
    )
    result = run_pipeline(req, provider)

    regenerate_case(
        req,
        "Verify raw overvoltage detection.",
        "normal_behavior",
        "Fix hard-rule failures.",
        provider,
        analysis=result.analysis,
    )

    _, regenerate_user_prompt = provider.calls[-1]
    assert "SUPP_ONLY_TOKEN" not in regenerate_user_prompt
    assert "BMS_CellOV_L3_Flag" not in regenerate_user_prompt
    assert "t_CellOV_Debounce" not in regenerate_user_prompt
