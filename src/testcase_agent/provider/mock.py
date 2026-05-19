class MockProvider:
    provider_name = "mock"
    model_name = "mock"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        phase = self._detect_phase(user_prompt)
        if phase == "analyze_and_plan":
            return self._mock_analyze_and_plan(user_prompt)
        return self._mock_generate_case(user_prompt)

    @staticmethod
    def _detect_phase(user_prompt: str) -> str:
        if "coverage plan" in user_prompt.lower() or "analyze the requirement" in user_prompt.lower():
            return "analyze_and_plan"
        return "generate_case"

    @staticmethod
    def _mock_analyze_and_plan(prompt: str) -> str:
        return """<analysis>
<section name="extracted_signals">BMS_ExampleFlag</section>
<section name="extracted_thresholds">r_Example_Threshold</section>
<section name="extracted_timing">t_Example_Debounce</section>
<section name="extracted_direction">trigger BMS_ExampleFlag</section>
<section name="missing_critical_info">none</section>
</analysis>
<coverage_plan>
<case_intent coverage="normal_behavior">Verify the basic positive trigger path of the requirement.</case_intent>
<case_intent coverage="boundary_or_threshold">Verify behavior at the threshold boundary.</case_intent>
</coverage_plan>"""

    @staticmethod
    def _mock_generate_case(prompt: str) -> str:
        return """<testcase>
<title>Draft Test Case</title>
<objective>Verify that the BMS satisfies the requirement under normal operating conditions.</objective>
<precondition>BMS is powered on and in normal operating mode.</precondition>
<steps>
<step order="1">
<action>Configure the system to the pre-condition state.</action>
<expected>System reports normal status.</expected>
</step>
<step order="2">
<action>Apply the stimulus described by the requirement.</action>
<expected>BMS_ExampleFlag = 1 within 100ms.</expected>
</step>
</steps>
<postcondition>System remains in a safe state.</postcondition>
</testcase>"""
