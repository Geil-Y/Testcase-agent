"""Tests for the ABC pipeline evaluator (checklist v2 hard-rule evaluation)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.testcase_agent.pipeline.evaluate import (
    _build_evaluation_results,
    _is_flat_case_list,
    _normalize_case,
    _wrap_flat_as_grouped,
    evaluate_generated_cases_file,
)
from optimization.evaluator import CaseEvaluation, EvaluationResult


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def run_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


# ── helper ────────────────────────────────────────────────────────────────


def _write_grouped_json(run_dir: Path, data: list[dict]) -> Path:
    path = run_dir / "generated_cases.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ── _is_flat_case_list ────────────────────────────────────────────────────


class TestIsFlatCaseList:
    def test_detects_flat_list(self):
        data = [{"title": "TC-01", "objective": "Verify X", "requirement_key": "R1"}]
        assert _is_flat_case_list(data) is True

    def test_rejects_grouped_list(self):
        data = [{"requirement_key": "R1", "analysis": {}, "cases": [{"title": "TC-01"}]}]
        assert _is_flat_case_list(data) is False

    def test_empty_list(self):
        assert _is_flat_case_list([]) is False


# ── _normalize_case ──────────────────────────────────────────────────────


class TestNormalizeCase:
    def test_maps_pre_condition_to_precondition(self):
        case = {"pre_condition": "Ready", "post_condition": "Done", "steps": []}
        out = _normalize_case(case, "R1")
        assert out["precondition"] == "Ready"
        assert out["postcondition"] == "Done"

    def test_maps_expected_result_to_expected_in_steps(self):
        case = {"steps": [{"action": "Set voltage", "expected_result": "Flag set"}]}
        out = _normalize_case(case, "R1")
        assert out["steps"][0]["expected"] == "Flag set"

    def test_sets_related_requirement_from_req_key(self):
        out = _normalize_case({}, "REQ-001")
        assert out["related_requirement"] == "REQ-001"


# ── _wrap_flat_as_grouped ─────────────────────────────────────────────────


class TestWrapFlatAsGrouped:
    def test_single_flat_case(self):
        flat = [{
            "title": "TC-01",
            "objective": "Verify X",
            "pre_condition": "Ready",
            "post_condition": "Done",
            "steps": [{"action": "Set voltage", "expected_result": "Flag set"}],
            "requirement_key": "REQ-001",
            "_analysis": {"signals": [], "thresholds": [], "timing": [], "missing_info_items": []},
        }]
        grouped = _wrap_flat_as_grouped(flat)
        assert len(grouped) == 1
        assert grouped[0]["requirement_key"] == "REQ-001"
        assert grouped[0]["cases"][0]["title"] == "TC-01"
        assert grouped[0]["cases"][0]["steps"][0]["expected"] == "Flag set"

    def test_preserves_analysis_metadata(self):
        analysis = {
            "signals": ["BMS_CellOV_Flag"],
            "thresholds": ["r_CellOV_Threshold"],
            "timing": [],
            "missing_info_items": [{"category": "timing", "description": "delay not given"}],
        }
        flat = [{"title": "TC-01", "steps": [], "requirement_key": "R1", "_analysis": analysis}]
        grouped = _wrap_flat_as_grouped(flat)
        assert grouped[0]["analysis"] == analysis

    def test_empty_flat_list(self):
        assert _wrap_flat_as_grouped([]) == []


# ── 2.2.1 — invented numeric value ──────────────────────────────────────


class TestInventedNumericValue:
    def test_fails_when_case_has_unauthorized_numeric_value(self, run_dir):
        """100V in case with no numeric authority → 2.2.1."""
        data = [{
            "requirement_key": "REQ-001",
            "description": "BMS detects overvoltage when cell voltage exceeds threshold.",
            "analysis": {
                "signals": ["BMS_CellOV_Detect"],
                "thresholds": ["r_CellOV_Threshold"],
                "timing": [],
                "missing_info_items": [],
                "case_intents": [{"coverage": "normal_behavior"}],
            },
            "cases": [{
                "title": "TC-01",
                "objective": "Verify overvoltage detection.",
                "precondition": "BMS initialized.",
                "postcondition": "System normal.",
                "steps": [{"action": "Set cell voltage to 100V", "expected": "BMS_CellOV_Detect == 1"}],
                "raw_html": "",
                "related_requirement": "REQ-001",
            }],
        }]
        _write_grouped_json(run_dir, data)

        evaluate_generated_cases_file(run_dir)

        results = json.loads((run_dir / "evaluation_results.json").read_text(encoding="utf-8"))
        assert results[0]["passed"] is False
        assert "2.2.1" in results[0]["failed_items"]

        hardrule = json.loads((run_dir / "hardrule_evaluation.json").read_text(encoding="utf-8"))
        assert hardrule["evaluated_by"] == "hardrule"
        assert hardrule["item_fail_counts"]["2.2.1"] >= 1


# ── 3.2.1 — missing [NEEDS REVIEW] ──────────────────────────────────────


class TestMissingNeedsReview:
    def test_fails_when_threshold_missing_but_no_nr_in_steps(self, run_dir):
        """Test basis has missing threshold; case lacks [NEEDS REVIEW] → 3.2.1."""
        data = [{
            "requirement_key": "REQ-002",
            "description": "Overvoltage detection with configurable threshold.",
            "analysis": {
                "signals": [],
                "thresholds": [],
                "timing": [],
                "missing_info_items": [
                    {"category": "threshold", "description": "OV threshold not provided"}
                ],
                "case_intents": [{"coverage": "normal_behavior"}],
            },
            "expected_missing_categories": ["threshold"],
            "cases": [{
                "title": "TC-02",
                "objective": "Verify OV response.",
                "precondition": "Ready.",
                "postcondition": "Done.",
                "steps": [{"action": "Set cell voltage above threshold", "expected": "OV flag set"}],
                "raw_html": "",
                "related_requirement": "REQ-002",
            }],
        }]
        _write_grouped_json(run_dir, data)

        evaluate_generated_cases_file(run_dir)

        results = json.loads((run_dir / "evaluation_results.json").read_text(encoding="utf-8"))
        assert results[0]["passed"] is False
        assert "3.2.1" in results[0]["failed_items"]


# ── honest [NEEDS REVIEW] allowed ───────────────────────────────────────


class TestHonestNeedsReviewAllowed:
    def test_passes_when_timing_missing_and_case_has_wait_nr(self, run_dir):
        """Timing missing + dedicated Wait [NEEDS REVIEW] step → no 3.2.1."""
        data = [{
            "requirement_key": "REQ-003",
            "description": "BMS detects overvoltage after debounce delay.",
            "analysis": {
                "signals": ["BMS_CellOV_Flag"],
                "thresholds": [],
                "timing": [],
                "missing_info_items": [
                    {"category": "timing", "description": "debounce delay not given"}
                ],
                "case_intents": [{"coverage": "normal_behavior"}],
            },
            "expected_missing_categories": ["timing"],
            "cases": [{
                "title": "TC-03",
                "objective": "Verify debounce behavior with honest timing gap.",
                "precondition": "Ready.",
                "postcondition": "Done.",
                "steps": [
                    {"action": "Set cell voltage above OV threshold", "expected": "Voltage above threshold"},
                    {"action": "Wait [NEEDS REVIEW]", "expected": "BMS_CellOV_Flag == 1"},
                ],
                "raw_html": "",
                "related_requirement": "REQ-003",
            }],
        }]
        _write_grouped_json(run_dir, data)

        evaluate_generated_cases_file(run_dir)

        results = json.loads((run_dir / "evaluation_results.json").read_text(encoding="utf-8"))
        assert "3.2.1" not in results[0]["failed_items"]


# ── artifact writing ────────────────────────────────────────────────────


class TestArtifactWriting:
    def test_writes_all_output_files(self, run_dir):
        data = [{
            "requirement_key": "REQ-004",
            "description": "Basic requirement.",
            "analysis": {
                "signals": [],
                "thresholds": [],
                "timing": [],
                "missing_info_items": [],
                "case_intents": [{"coverage": "normal_behavior"}],
            },
            "cases": [{
                "title": "TC-04",
                "objective": "Check basic behavior.",
                "precondition": "Ready.",
                "postcondition": "Done.",
                "steps": [{"action": "Wait 100ms", "expected": "Flag == 1"}],
                "raw_html": "",
                "related_requirement": "REQ-004",
            }],
        }]
        _write_grouped_json(run_dir, data)

        evaluate_generated_cases_file(run_dir)

        assert (run_dir / "evaluation_results.json").exists()
        assert (run_dir / "evaluation_summary.json").exists()

        summary = json.loads((run_dir / "evaluation_summary.json").read_text(encoding="utf-8"))
        assert summary["total_cases"] == 1
        assert "passed" in summary
        assert "failed" in summary
        assert "pass_rate" in summary

    def test_writes_hardrule_evaluation_json(self, run_dir):
        data = [{
            "requirement_key": "REQ-005",
            "description": "Simple requirement.",
            "analysis": {
                "signals": [],
                "thresholds": [],
                "timing": [],
                "missing_info_items": [],
                "case_intents": [{"coverage": "normal_behavior"}],
            },
            "cases": [{
                "title": "TC-05",
                "objective": "Simple check.",
                "precondition": "Ready.",
                "postcondition": "Done.",
                "steps": [{"action": "Wait 100ms", "expected": "Flag == 1"}],
                "raw_html": "",
                "related_requirement": "REQ-005",
            }],
        }]
        _write_grouped_json(run_dir, data)

        evaluate_generated_cases_file(run_dir)

        hardrule_path = run_dir / "hardrule_evaluation.json"
        assert hardrule_path.exists()

        hardrule = json.loads(hardrule_path.read_text(encoding="utf-8"))
        assert hardrule["evaluated_by"] == "hardrule"
        assert hardrule["total_cases"] == 1
        assert "item_fail_counts" in hardrule
        assert "item_warning_counts" in hardrule
        assert "cases" in hardrule


# ── FileNotFoundError ───────────────────────────────────────────────────


class TestFileNotFound:
    def test_raises_when_generated_cases_missing(self, run_dir):
        with pytest.raises(FileNotFoundError, match="generated_cases.json"):
            evaluate_generated_cases_file(run_dir)


# ── _build_evaluation_results ──────────────────────────────────────────


class TestBuildEvaluationResults:
    def test_passed_case(self):
        result = EvaluationResult(total_cases=1, total_passed=1)
        result.case_results[("REQ-001", 0)] = CaseEvaluation(
            requirement_key="REQ-001", case_index=0, case_title="TC-01",
        )
        out = _build_evaluation_results(result)
        assert len(out) == 1
        assert out[0]["passed"] is True
        assert out[0]["failed_items"] == []

    def test_failed_case(self):
        result = EvaluationResult(total_cases=1, total_passed=0)
        result.case_results[("REQ-001", 0)] = CaseEvaluation(
            requirement_key="REQ-001", case_index=0, case_title="TC-01",
            failed_items=["2.2.1", "3.2.1"],
        )
        out = _build_evaluation_results(result)
        assert out[0]["passed"] is False
        assert "2.2.1" in out[0]["failed_items"]
        assert "3.2.1" in out[0]["failed_items"]


# ── no review_pipeline dependency ──────────────────────────────────────


def test_evaluator_module_does_not_import_review_pipeline():
    """The ABC evaluator must not depend on testcase_agent.review_pipeline."""
    from src.testcase_agent.pipeline import evaluate as mod

    source = Path(mod.__file__).read_text(encoding="utf-8")
    assert "testcase_agent.review_pipeline" not in source
