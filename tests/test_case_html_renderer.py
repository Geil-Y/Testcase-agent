"""Tests for case display HTML rendering."""

import json
from collections import Counter

from optimization import generate_case_html
from optimization.evaluator import CaseEvaluation, EvaluationResult


def _generated_data() -> list[dict]:
    return [{
        "requirement_key": "REQ-001",
        "function_name": "Protection",
        "description": "Requirement with complete information.",
        "supplementary_info": "",
        "analysis": {
            "signals": [],
            "thresholds": [],
            "timing": [],
            "states": [],
            "observations": [],
            "missing_info_items": [],
            "case_intents": [
                {"coverage": "normal_behavior", "description": "Verify normal behavior"}
            ],
        },
        "cases": [{
            "title": "TC-01",
            "objective": "Verify requirement behavior",
            "precondition": "BMS initialized, all parameters within normal operating range, no active faults.",
            "postcondition": "System returned to normal operating state.",
            "related_requirement": "REQ-001",
            "steps": [
                {"order": 1, "action": "Set input", "expected": "Protection flag becomes active"}
            ],
            "raw_html": "",
        }],
    }]


def test_generate_round_html_uses_evaluation_engine_result(tmp_path, monkeypatch):
    round_dir = tmp_path / "round_01"
    round_dir.mkdir()
    (round_dir / "generated_cases.json").write_text(
        json.dumps(_generated_data()),
        encoding="utf-8",
    )

    fake = EvaluationResult(
        total_cases=1,
        total_passed=0,
        case_pass_rate=0.0,
        case_results={
            ("REQ-001", 0): CaseEvaluation(
                requirement_key="REQ-001",
                case_index=0,
                case_title="TC-01",
                failed_items=["3.2.1"],
            )
        },
        item_fail_counts=Counter({"3.2.1": 1}),
    )

    monkeypatch.setattr(generate_case_html, "evaluate_generated_cases", lambda data: fake)
    monkeypatch.setattr(generate_case_html, "load_all_evaluations", lambda rd: {})

    generate_case_html.generate_round_html(round_dir, 1)

    html = (round_dir / "cases_report.html").read_text(encoding="utf-8")
    assert "FAIL" in html
    assert "3.2.1" in html


def test_generate_round_html_renders_nested_8d_evaluation(tmp_path, monkeypatch):
    round_dir = tmp_path / "round_01"
    round_dir.mkdir()
    (round_dir / "generated_cases.json").write_text(
        json.dumps(_generated_data()),
        encoding="utf-8",
    )

    fake = EvaluationResult(
        total_cases=1,
        total_passed=1,
        case_pass_rate=100.0,
        case_results={
            ("REQ-001", 0): CaseEvaluation(
                requirement_key="REQ-001",
                case_index=0,
                case_title="TC-01",
                failed_items=[],
            )
        },
    )
    deepseek = {
        "schema_version": "score-v2-8d",
        "dimension_averages": {"requirement_alignment": 5},
        "overall_weighted": 4.6,
        "total_requirements": 1,
        "requirements": [{
            "requirement_key": "REQ-001",
            "coverage_value": 4,
            "coverage_value_note": "Coverage is good.",
            "cases": [{
                "case_index": 0,
                "case_title": "TC-01",
                "requirement_alignment": 5,
                "requirement_alignment_note": "Aligned.",
                "information_integrity": 5,
                "information_integrity_note": "No invented values.",
                "executability": 4,
                "observability": 4,
                "pass_fail_clarity": 4,
                "state_and_environment_control": 4,
                "automation_readiness": 4,
            }],
        }],
    }

    monkeypatch.setattr(generate_case_html, "evaluate_generated_cases", lambda data: fake)
    monkeypatch.setattr(generate_case_html, "load_all_evaluations", lambda rd: {"deepseek": deepseek})

    generate_case_html.generate_round_html(round_dir, 1)

    html = (round_dir / "cases_report.html").read_text(encoding="utf-8")
    assert "DeepSeek weighted / 5 (1 requirements)" in html
    assert "Requirement Alignment" in html
    assert "Information Integrity" in html
    assert "Coverage Value" in html
