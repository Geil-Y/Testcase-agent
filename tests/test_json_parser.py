import pytest

from testcase_agent.parser.json_parser import (
    CaseIntentPlan,
    MissingInfoItem,
    PlannedCaseIntent,
    TestBasis,
    parse_case_intents_json,
    parse_test_basis_json,
)


class TestParseTestBasisJson:
    def test_parses_valid_test_basis(self):
        raw = """{
            "requirement_key": "REQ-001",
            "allowed_signals": ["BMS_CellOV_Detect"],
            "allowed_thresholds": ["r_CellOV_Threshold"],
            "allowed_timing": [],
            "allowed_states": [],
            "allowed_observations": [],
            "missing_info": [
                {"category": "timing", "description": "response timing not specified"}
            ]
        }"""

        basis = parse_test_basis_json(raw)

        assert basis.requirement_key == "REQ-001"
        assert basis.allowed_signals == ["BMS_CellOV_Detect"]
        assert basis.allowed_thresholds == ["r_CellOV_Threshold"]
        assert basis.allowed_timing == []
        assert basis.allowed_states == []
        assert basis.allowed_observations == []
        assert len(basis.missing_info) == 1
        assert basis.missing_info[0].category == "timing"
        assert basis.missing_info[0].description == "response timing not specified"

    def test_empty_missing_info(self):
        raw = """{
            "requirement_key": "REQ-002",
            "allowed_signals": [],
            "allowed_thresholds": [],
            "allowed_timing": [],
            "allowed_states": [],
            "allowed_observations": [],
            "missing_info": []
        }"""

        basis = parse_test_basis_json(raw)

        assert basis.requirement_key == "REQ-002"
        assert basis.missing_info == []

    def test_strips_json_fence(self):
        raw = """```json
        {
            "requirement_key": "REQ-003",
            "allowed_signals": [],
            "allowed_thresholds": [],
            "allowed_timing": [],
            "allowed_states": [],
            "allowed_observations": [],
            "missing_info": []
        }
        ```"""

        basis = parse_test_basis_json(raw)
        assert basis.requirement_key == "REQ-003"

    def test_strips_fence_without_lang_label(self):
        raw = """```
        {
            "requirement_key": "REQ-004",
            "allowed_signals": [],
            "allowed_thresholds": [],
            "allowed_timing": [],
            "allowed_states": [],
            "allowed_observations": [],
            "missing_info": []
        }
        ```"""

        basis = parse_test_basis_json(raw)
        assert basis.requirement_key == "REQ-004"

    def test_rejects_invalid_missing_info_category(self):
        raw = """{
            "requirement_key": "REQ-005",
            "allowed_signals": [],
            "allowed_thresholds": [],
            "allowed_timing": [],
            "allowed_states": [],
            "allowed_observations": [],
            "missing_info": [
                {"category": "unknown_field", "description": "something"}
            ]
        }"""

        with pytest.raises(ValueError, match="missing_info\\[0\\].category must be one of"):
            parse_test_basis_json(raw)

    def test_rejects_missing_requirement_key(self):
        raw = """{
            "allowed_signals": [],
            "allowed_thresholds": [],
            "allowed_timing": [],
            "allowed_states": [],
            "allowed_observations": [],
            "missing_info": []
        }"""

        with pytest.raises(ValueError, match="requirement_key is required"):
            parse_test_basis_json(raw)

    def test_rejects_non_object_input(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            parse_test_basis_json("[]")

    def test_rejects_invalid_json(self):
        with pytest.raises(ValueError, match="LLM-A JSON parse error"):
            parse_test_basis_json("not json")

    def test_all_valid_missing_info_categories_accepted(self):
        for cat in ("signal", "threshold", "timing", "state", "observation"):
            raw = f"""{{
                "requirement_key": "REQ-006",
                "allowed_signals": [],
                "allowed_thresholds": [],
                "allowed_timing": [],
                "allowed_states": [],
                "allowed_observations": [],
                "missing_info": [
                    {{"category": "{cat}", "description": "test description"}}
                ]
            }}"""
            basis = parse_test_basis_json(raw)
            assert basis.missing_info[0].category == cat

    def test_rejects_missing_info_not_a_list(self):
        raw = """{
            "requirement_key": "REQ-007",
            "allowed_signals": [],
            "allowed_thresholds": [],
            "allowed_timing": [],
            "allowed_states": [],
            "allowed_observations": [],
            "missing_info": "not a list"
        }"""

        with pytest.raises(ValueError, match="missing_info must be a list"):
            parse_test_basis_json(raw)

    def test_rejects_missing_info_item_not_an_object(self):
        raw = """{
            "requirement_key": "REQ-008",
            "allowed_signals": [],
            "allowed_thresholds": [],
            "allowed_timing": [],
            "allowed_states": [],
            "allowed_observations": [],
            "missing_info": ["not an object"]
        }"""

        with pytest.raises(ValueError, match="must be an object"):
            parse_test_basis_json(raw)

    def test_coerces_dict_list_items_to_string(self):
        raw = """{
            "requirement_key": "REQ-009",
            "allowed_signals": [{"name": "BMS_CellOV_Detect"}],
            "allowed_thresholds": [],
            "allowed_timing": [],
            "allowed_states": [],
            "allowed_observations": [],
            "missing_info": []
        }"""

        basis = parse_test_basis_json(raw)
        assert basis.allowed_signals == ["BMS_CellOV_Detect"]

    def test_coerces_non_string_list_items_to_string(self):
        raw = """{
            "requirement_key": "REQ-010",
            "allowed_signals": [123],
            "allowed_thresholds": [],
            "allowed_timing": [],
            "allowed_states": [],
            "allowed_observations": [],
            "missing_info": []
        }"""

        basis = parse_test_basis_json(raw)
        assert basis.allowed_signals == ["123"]


class TestParseCaseIntentsJson:
    def test_parses_valid_case_intents(self):
        raw = """{
            "requirement_key": "REQ-001",
            "case_intents": [
                {
                    "intent_id": "intent-1",
                    "coverage_dimension": "normal_behavior",
                    "intent_text": "Verify raw overvoltage detection."
                },
                {
                    "intent_id": "intent-2",
                    "coverage_dimension": "boundary_or_threshold",
                    "intent_text": "Verify threshold boundary behavior."
                }
            ]
        }"""

        plan = parse_case_intents_json(raw)

        assert plan.requirement_key == "REQ-001"
        assert len(plan.case_intents) == 2
        assert plan.case_intents[0].intent_id == "intent-1"
        assert plan.case_intents[0].coverage_dimension == "normal_behavior"
        assert plan.case_intents[0].intent_text == "Verify raw overvoltage detection."
        assert plan.case_intents[1].intent_id == "intent-2"
        assert plan.case_intents[1].coverage_dimension == "boundary_or_threshold"

    def test_strips_json_fence(self):
        raw = """```json
        {
            "requirement_key": "REQ-002",
            "case_intents": [
                {
                    "intent_id": "intent-1",
                    "coverage_dimension": "normal_behavior",
                    "intent_text": "Verify basic operation."
                }
            ]
        }
        ```"""

        plan = parse_case_intents_json(raw)
        assert plan.requirement_key == "REQ-002"
        assert len(plan.case_intents) == 1

    def test_rejects_invalid_coverage_dimension(self):
        raw = """{
            "requirement_key": "REQ-003",
            "case_intents": [
                {
                    "intent_id": "intent-1",
                    "coverage_dimension": "invalid_dimension",
                    "intent_text": "Verify something."
                }
            ]
        }"""

        with pytest.raises(ValueError, match="coverage_dimension must be one of"):
            parse_case_intents_json(raw)

    def test_rejects_missing_requirement_key(self):
        raw = """{
            "case_intents": []
        }"""

        with pytest.raises(ValueError, match="requirement_key is required"):
            parse_case_intents_json(raw)

    def test_rejects_non_object_input(self):
        with pytest.raises(ValueError, match="must be a JSON object"):
            parse_case_intents_json("[]")

    def test_rejects_invalid_json(self):
        with pytest.raises(ValueError, match="LLM-B JSON parse error"):
            parse_case_intents_json("not json")

    def test_empty_intent_list(self):
        raw = """{
            "requirement_key": "REQ-004",
            "case_intents": []
        }"""

        plan = parse_case_intents_json(raw)
        assert plan.requirement_key == "REQ-004"
        assert plan.case_intents == []

    def test_all_valid_coverage_dimensions_accepted(self):
        for dim in (
            "normal_behavior",
            "boundary_or_threshold",
            "fault_or_protection",
            "state_transition",
            "observability",
        ):
            raw = f"""{{
                "requirement_key": "REQ-005",
                "case_intents": [
                    {{
                        "intent_id": "intent-1",
                        "coverage_dimension": "{dim}",
                        "intent_text": "Verify something."
                    }}
                ]
            }}"""
            plan = parse_case_intents_json(raw)
            assert plan.case_intents[0].coverage_dimension == dim


class TestMissingInfoItem:
    def test_missing_info_item_creation(self):
        item = MissingInfoItem(category="timing", description="response time not given")
        assert item.category == "timing"
        assert item.description == "response time not given"


class TestTestBasisDefaults:
    def test_test_basis_defaults(self):
        basis = TestBasis(requirement_key="REQ-X")
        assert basis.requirement_key == "REQ-X"
        assert basis.allowed_signals == []
        assert basis.missing_info == []


class TestPlannedCaseIntent:
    def test_planned_case_intent_creation(self):
        intent = PlannedCaseIntent(
            intent_id="intent-1",
            coverage_dimension="normal_behavior",
            intent_text="Verify basic operation.",
        )
        assert intent.intent_id == "intent-1"
        assert intent.coverage_dimension == "normal_behavior"


class TestCaseIntentPlan:
    def test_case_intent_plan_defaults(self):
        plan = CaseIntentPlan(requirement_key="REQ-X")
        assert plan.requirement_key == "REQ-X"
        assert plan.case_intents == []
