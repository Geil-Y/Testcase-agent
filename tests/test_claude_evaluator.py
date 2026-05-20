"""Tests for the DeepSeek 8-dimension evaluator data model."""

import json

from optimization.claude_evaluator import (
    CaseScore,
    EvalResult,
    RequirementScore,
    _build_user_prompt,
    _parse_requirement_scores,
    save_evaluation,
)


def test_parse_nested_requirement_scores():
    parsed = {
        "requirements": [{
            "requirement_key": "R1",
            "coverage_value": 4,
            "coverage_value_note": "Good case-set coverage.",
            "cases": [{
                "case_index": 0,
                "case_title": "TC-01",
                "requirement_alignment": 5,
                "requirement_alignment_note": "Aligned.",
                "executability": 4,
                "observability": 3,
                "pass_fail_clarity": 3,
                "information_integrity": 5,
                "state_and_environment_control": 4,
                "automation_readiness": 4,
            }],
        }],
    }

    scores = _parse_requirement_scores(parsed)

    assert len(scores) == 1
    assert scores[0].requirement_key == "R1"
    assert scores[0].coverage_value == 4
    assert scores[0].cases[0].requirement_alignment == 5
    assert scores[0].cases[0].information_integrity == 5


def test_eval_result_averages_per_requirement():
    result = EvalResult(requirements=[
        RequirementScore(
            requirement_key="R1",
            coverage_value=5,
            cases=[
                CaseScore("R1", 0, "TC-01", requirement_alignment=5, executability=5,
                          observability=5, pass_fail_clarity=5, information_integrity=5,
                          state_and_environment_control=5, automation_readiness=5),
                CaseScore("R1", 1, "TC-02", requirement_alignment=5, executability=5,
                          observability=5, pass_fail_clarity=5, information_integrity=5,
                          state_and_environment_control=5, automation_readiness=5),
            ],
        ),
        RequirementScore(
            requirement_key="R2",
            coverage_value=1,
            cases=[
                CaseScore("R2", 0, "TC-01", requirement_alignment=1, executability=1,
                          observability=1, pass_fail_clarity=1, information_integrity=1,
                          state_and_environment_control=1, automation_readiness=1),
            ],
        ),
    ])

    assert result.total_requirements == 2
    assert result.total_cases == 3
    assert result.dimension_averages["coverage_value"] == 3.0
    assert result.dimension_averages["requirement_alignment"] == 3.0
    assert result.overall_weighted == 3.0


def test_save_evaluation_writes_nested_and_flattened_cases(tmp_path):
    result = EvalResult(
        model_used="test-model",
        requirements=[
            RequirementScore(
                requirement_key="R1",
                coverage_value=4,
                coverage_value_note="Coverage note.",
                cases=[
                    CaseScore("R1", 0, "TC-01", requirement_alignment=5, executability=4,
                              observability=4, pass_fail_clarity=3, information_integrity=5,
                              state_and_environment_control=4, automation_readiness=4),
                ],
            )
        ],
    )

    out = save_evaluation(result, tmp_path, evaluator_name="deepseek")
    data = json.loads(out.read_text(encoding="utf-8"))

    assert data["schema_version"] == "score-v2-8d"
    assert data["total_requirements"] == 1
    assert data["requirements"][0]["coverage_value"] == 4
    assert data["cases"][0]["coverage_value"] == 4
    assert data["cases"][0]["information_integrity"] == 5


def test_user_prompt_contains_requirement_group_test_basis():
    requirements = [{
        "requirement_key": "R1",
        "function_name": "Protection",
        "description": "Detect overvoltage.",
        "supplementary_info": "Threshold parameter: V_OV.",
        "expected_missing_categories": ["timing"],
        "analysis": {
            "signals": ["CellVoltage"],
            "thresholds": ["V_OV"],
            "timing": [],
            "states": ["Normal"],
            "observations": ["OV flag"],
            "missing_info_items": [{"category": "timing", "description": "debounce missing"}],
            "case_intents": [{"coverage": "positive_trigger", "description": "trigger OV"}],
        },
        "cases": [{
            "title": "TC-01",
            "objective": "Verify OV trigger",
            "precondition": "Normal",
            "postcondition": "Restored",
            "steps": [{"order": 1, "action": "Set CellVoltage to V_OV", "expected": "OV flag active"}],
        }],
    }]

    prompt = _build_user_prompt(requirements, 0, 1)

    assert "Description: Detect overvoltage." in prompt
    assert "Known signals: CellVoltage" in prompt
    assert "Expected missing categories: timing" in prompt
    assert "Coverage plan" in prompt
    assert "Case intent: trigger OV" in prompt
