"""Tests for Prompt Learning framework validation."""

from testcase_agent.prompt_learning.framework_validation import validate_prompt_set


def make_valid_prompt_set() -> dict[str, str]:
    """Return a minimal valid prompt set with all required template variables."""
    return {
        "analyze_test_basis.system.html": (
            '<p>Analyze requirement {{ requirement_key }}: {{ description }}.</p>'
            '<p>Output JSON.</p>'
        ),
        "analyze_test_basis.user.html": (
            '<p>Requirement: {{ requirement_key }} - {{ description }}</p>'
        ),
        "plan_case_intents.system.html": (
            '<p>Plan intents for {{ requirement_key }}: {{ description }}.</p>'
            '<p>Signals: {{ allowed_signals }}</p>'
            '<p>Thresholds: {{ allowed_thresholds }}</p>'
            '<p>Timing: {{ allowed_timing }}</p>'
            '<p>States: {{ allowed_states }}</p>'
            '<p>Observations: {{ allowed_observations }}</p>'
            '<p>Missing info: {{ missing_info }}</p>'
            '<p>Output JSON.</p>'
        ),
        "plan_case_intents.user.html": (
            '<p>{{ requirement_key }} - {{ description }}</p>'
        ),
        "generate_case.system.html": (
            '<p>Generate case for {{ requirement_key }}: {{ description }}.</p>'
            '<p>Supplementary: {{ supplementary_info }}</p>'
            '<p>Dimension: {{ coverage_dimension }}</p>'
            '<p>Intent: {{ case_intent }}</p>'
            '<p>Review: {{ review_comment }}</p>'
            '<p>Signals: {{ extracted_signals }}</p>'
            '<p>Thresholds: {{ extracted_thresholds }}</p>'
            '<p>Timing: {{ extracted_timing }}</p>'
            '<p>States: {{ extracted_states }}</p>'
            '<p>Observations: {{ extracted_observations }}</p>'
            '<p>Missing: {{ missing_info }}</p>'
            '<p>Missing items: {{ missing_info_items }}</p>'
            '<p>Output <testcase> tag.</p>'
        ),
        "generate_case.user.html": (
            '<p>{{ requirement_key }} - {{ description }}</p>'
        ),
    }


class TestValidPromptSet:
    def test_valid_set_passes(self):
        result = validate_prompt_set(make_valid_prompt_set())
        assert result.valid is True
        assert result.errors == []


class TestMissingFile:
    def test_missing_file_reported(self):
        files = make_valid_prompt_set()
        del files["generate_case.user.html"]
        result = validate_prompt_set(files)
        assert result.valid is False
        assert any("generate_case.user.html" in e.filename for e in result.errors)
        assert any("Missing required" in e.message for e in result.errors)


class TestExtraFile:
    def test_extra_file_reported(self):
        files = make_valid_prompt_set()
        files["extra_file.html"] = "content"
        result = validate_prompt_set(files)
        assert result.valid is False
        assert any("extra_file.html" in e.filename for e in result.errors)


class TestMissingVariables:
    def test_missing_required_variable_reported(self):
        files = make_valid_prompt_set()
        # Remove {{ description }} from LLM-A system AND user files
        files["analyze_test_basis.system.html"] = (
            '<p>Analyze {{ requirement_key }} only. Output JSON.</p>'
        )
        files["analyze_test_basis.user.html"] = (
            '<p>Requirement: {{ requirement_key }}</p>'
        )
        result = validate_prompt_set(files)
        assert result.valid is False
        assert any("description" in e.message for e in result.errors)

    def test_missing_variable_in_llm_b(self):
        files = make_valid_prompt_set()
        # Remove {{ allowed_signals }}
        files["plan_case_intents.system.html"] = (
            '<p>{{ requirement_key }}: {{ description }}. Output JSON.</p>'
        )
        result = validate_prompt_set(files)
        assert result.valid is False
        assert any("allowed_signals" in e.message for e in result.errors)


class TestJsonOutputRequirement:
    def test_missing_json_in_llm_a(self):
        files = make_valid_prompt_set()
        files["analyze_test_basis.system.html"] = files["analyze_test_basis.system.html"].replace("JSON", "XML")
        files["analyze_test_basis.user.html"] = ""
        result = validate_prompt_set(files)
        assert result.valid is False
        assert any("LLM-A" in e.message and "JSON" in e.message for e in result.errors)

    def test_missing_json_in_llm_b(self):
        files = make_valid_prompt_set()
        files["plan_case_intents.system.html"] = files["plan_case_intents.system.html"].replace("JSON", "")
        result = validate_prompt_set(files)
        assert result.valid is False
        assert any("LLM-B" in e.message and "JSON" in e.message for e in result.errors)


class TestTestcaseTagRequirement:
    def test_missing_testcase_tag_in_llm_c(self):
        files = make_valid_prompt_set()
        files["generate_case.system.html"] = (
            '<p>{{ requirement_key }}: {{ description }}. No testcase tag here.</p>'
        )
        result = validate_prompt_set(files)
        assert result.valid is False
        assert any("generate_case" in e.filename and "testcase" in e.message.lower() for e in result.errors)

    def test_testcase_tag_present_is_valid(self):
        files = make_valid_prompt_set()
        files["generate_case.system.html"] = '<p>Use <testcase> tag.</p>'
        result = validate_prompt_set(files)
        # This will fail on other things (missing vars) but testcase should be OK
        assert not any("testcase" in e.message.lower() for e in result.errors)
