"""Tests for deterministic prompt debug report CLI."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from optimization.prompt_debug_report import (
    load_round,
    compute_hardrule_fail_ranking,
    compute_all_fail_requirements,
    compute_retry_summary,
    compute_missing_category_mismatches,
    compute_case_count_distribution,
    generate_report,
)
from optimization.evaluator import CHECKLIST


# ── Fixture helpers ────────────────────────────────────────────────────────


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _make_summary(total_req: int = 2, total_cases: int = 4, errors: int = 0) -> dict:
    return {"total_requirements": total_req, "total_cases": total_cases, "errors": errors}


def _make_generated_cases(*reqs: dict) -> list[dict]:
    return list(reqs)


def _make_req(
    key: str = "REQ-001",
    cases: list[dict] | None = None,
    expected_missing: list[str] | None = None,
    actual_missing: list[dict] | None = None,
    bucket: str = "test-bucket",
) -> dict:
    return {
        "requirement_key": key,
        "function_name": "TestFunc",
        "description": f"Requirement {key} description.",
        "evaluation_bucket": bucket,
        "expected_missing_categories": expected_missing or [],
        "analysis": {
            "signals": ["SIG_1"],
            "thresholds": [],
            "timing": [],
            "states": [],
            "observations": [],
            "missing_info_items": actual_missing or [],
            "case_intents": [],
        },
        "cases": cases or [],
    }


def _make_case(
    title: str = "TC-01",
    passed: bool = True,
    retry_attempts: int = 0,
    retry_exhausted: bool = False,
    steps: list[dict] | None = None,
) -> dict:
    return {
        "title": title,
        "objective": "Verify something",
        "precondition": "BMS ready",
        "postcondition": "Normal state",
        "related_requirement": "REQ-001",
        "steps": steps or [{"order": 1, "action": "Do X", "expected": "OK"}],
        "quality": {"passed": passed, "failures": [], "warnings": []},
        "retry": {"attempts": retry_attempts, "exhausted": retry_exhausted},
    }


def _make_hardrule_eval(cases: list[dict] | None = None, item_fail_counts: dict | None = None,
                         total_cases: int = 4, total_passed: int = 2) -> dict:
    return {
        "checklist_version": "checklist_v2.md",
        "evaluated_by": "hardrule",
        "total_cases": total_cases,
        "total_passed": total_passed,
        "case_pass_rate": round(total_passed / total_cases * 100, 1) if total_cases else 0,
        "errors": 0,
        "item_fail_counts": item_fail_counts or {},
        "item_warning_counts": {},
        "cases": cases or [],
    }


def _make_hr_case(req_key: str = "REQ-001", case_idx: int = 0, title: str = "TC-01",
                  failed_items: list[str] | None = None) -> dict:
    items: list[dict] = []
    failed_set = set(failed_items or [])
    for item_id in CHECKLIST:
        if item_id in failed_set:
            items.append({"item_id": item_id, "result": "fail", "note": ""})
        else:
            items.append({"item_id": item_id, "result": "pass", "note": ""})
    return {
        "requirement_key": req_key,
        "case_index": case_idx,
        "case_title": title,
        "items": items,
    }


def _make_deepseek_eval(
    overall_weighted: float = 3.5,
    dimension_averages: dict | None = None,
    total_requirements: int = 2,
    total_cases: int = 4,
    errors: int = 0,
    requirements: list[dict] | None = None,
) -> dict:
    return {
        "schema_version": "score-v2-8d",
        "evaluated_by": "deepseek",
        "model": "test-model",
        "weights": {
            "requirement_alignment": 0.20,
            "information_integrity": 0.20,
            "executability": 0.15,
            "observability": 0.15,
            "pass_fail_clarity": 0.10,
            "coverage_value": 0.10,
            "state_and_environment_control": 0.05,
            "automation_readiness": 0.05,
        },
        "total_requirements": total_requirements,
        "total_cases": total_cases,
        "errors": errors,
        "dimension_averages": dimension_averages or {
            "requirement_alignment": 4.0,
            "coverage_value": 3.5,
            "executability": 3.2,
            "observability": 3.0,
            "pass_fail_clarity": 3.5,
            "information_integrity": 4.0,
            "state_and_environment_control": 3.5,
            "automation_readiness": 3.0,
        },
        "overall_weighted": overall_weighted,
        "requirements": requirements or [],
    }


# ── Tests ──────────────────────────────────────────────────────────────────


class TestLoadRound:
    def test_reads_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_json(d / "summary.json", _make_summary(2, 4))
            _write_json(d / "generated_cases.json", [
                _make_req("REQ-001", [_make_case("TC-01")]),
                _make_req("REQ-002", [_make_case("TC-02")]),
            ])
            _write_json(d / "hardrule_evaluation.json",
                        _make_hardrule_eval(total_cases=2, total_passed=1))

            data = load_round(d)

            assert data["summary"]["total_requirements"] == 2
            assert len(data["generated_cases"]) == 2
            assert data["hardrule_evaluation"]["total_cases"] == 2
            assert data["deepseek_evaluation"] is None

    def test_handles_missing_deepseek(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_json(d / "summary.json", _make_summary())
            _write_json(d / "generated_cases.json", [])
            _write_json(d / "hardrule_evaluation.json", _make_hardrule_eval())

            data = load_round(d)
            assert data["deepseek_evaluation"] is None

    def test_loads_deepseek_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_json(d / "summary.json", _make_summary())
            _write_json(d / "generated_cases.json", [])
            _write_json(d / "hardrule_evaluation.json", _make_hardrule_eval())
            _write_json(d / "deepseek_evaluation.json",
                        _make_deepseek_eval(overall_weighted=3.0))

            data = load_round(d)
            assert data["deepseek_evaluation"] is not None
            assert data["deepseek_evaluation"]["overall_weighted"] == 3.0

    def test_raises_when_required_file_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_json(d / "summary.json", _make_summary())
            # Missing generated_cases.json
            with pytest.raises(FileNotFoundError):
                load_round(d)


class TestHardruleFailRanking:
    def test_sorts_descending_by_fail_count(self):
        hr = _make_hardrule_eval(item_fail_counts={
            "4.1.1": 10, "3.2.1": 5, "2.1.1": 8, "4.1.4": 1,
        })
        ranking = compute_hardrule_fail_ranking(hr)
        # ranking is list of (item_id, fail_count, description)
        counts = [r[1] for r in ranking]
        assert counts == sorted(counts, reverse=True)
        assert ranking[0][0] == "4.1.1"

    def test_includes_known_descriptions(self):
        hr = _make_hardrule_eval(item_fail_counts={"3.2.1": 3})
        ranking = compute_hardrule_fail_ranking(hr)
        assert len(ranking) == 1
        assert ranking[0][0] == "3.2.1"
        assert "NEEDS REVIEW" in ranking[0][2]

    def test_handles_unknown_item_id(self):
        hr = _make_hardrule_eval(item_fail_counts={"9.9.9": 5})
        ranking = compute_hardrule_fail_ranking(hr)
        assert len(ranking) == 1
        assert ranking[0][0] == "9.9.9"
        assert ranking[0][2] == "(description not available)"

    def test_empty_when_no_failures(self):
        hr = _make_hardrule_eval(item_fail_counts={})
        ranking = compute_hardrule_fail_ranking(hr)
        assert ranking == []


class TestAllFailRequirements:
    def test_detects_requirement_where_all_cases_failed(self):
        hr = _make_hardrule_eval(
            total_cases=3,
            total_passed=0,
            cases=[
                _make_hr_case("REQ-A", 0, "TC-01", ["3.2.1"]),
                _make_hr_case("REQ-A", 1, "TC-02", ["4.1.1"]),
                _make_hr_case("REQ-B", 0, "TC-03"),  # no failures
            ],
        )
        generated = [
            _make_req("REQ-A", [_make_case("TC-01", False), _make_case("TC-02", False)]),
            _make_req("REQ-B", [_make_case("TC-03", True)]),
        ]
        results = compute_all_fail_requirements(generated, hr)

        all_fail_keys = [r["requirement_key"] for r in results["all_fail_requirements"]]
        assert "REQ-A" in all_fail_keys
        assert "REQ-B" not in all_fail_keys

    def test_no_all_fail_when_some_pass(self):
        hr = _make_hardrule_eval(
            total_cases=2,
            total_passed=1,
            cases=[
                _make_hr_case("REQ-A", 0, "TC-01", ["3.2.1"]),
                _make_hr_case("REQ-A", 1, "TC-02"),  # passes
            ],
        )
        generated = [
            _make_req("REQ-A", [_make_case("TC-01", False), _make_case("TC-02", True)]),
        ]
        results = compute_all_fail_requirements(generated, hr)
        assert len(results["all_fail_requirements"]) == 0


class TestRetrySummary:
    def test_aggregates_retry_counts(self):
        generated = [
            _make_req("REQ-001", [
                _make_case("TC-01", retry_attempts=2, retry_exhausted=True),
                _make_case("TC-02", retry_attempts=1, retry_exhausted=False),
            ]),
            _make_req("REQ-002", [
                _make_case("TC-03", retry_attempts=0, retry_exhausted=False),
            ]),
        ]
        summary = compute_retry_summary(generated)

        assert summary["total_retried"] == 2
        assert summary["total_exhausted"] == 1
        assert "REQ-001" in summary["reqs_with_retries"]
        assert "REQ-002" not in summary["reqs_with_retries"]
        assert "REQ-001" in summary["reqs_with_exhausted"]

    def test_no_retries_when_none_present(self):
        generated = [
            _make_req("REQ-001", [_make_case("TC-01")]),
        ]
        summary = compute_retry_summary(generated)
        assert summary["total_retried"] == 0
        assert summary["total_exhausted"] == 0

    def test_handles_case_without_retry_field(self):
        case_no_retry = {
            "title": "TC-01", "objective": "X", "precondition": "Y",
            "postcondition": "Z", "related_requirement": "REQ-001",
            "steps": [], "quality": {"passed": True},
        }
        generated = [_make_req("REQ-001", [case_no_retry])]
        summary = compute_retry_summary(generated)
        assert summary["total_retried"] == 0
        assert summary["total_exhausted"] == 0


class TestMissingCategoryMismatches:
    def test_detects_mismatch(self):
        generated = [
            _make_req("REQ-001",
                      expected_missing=["timing", "threshold"],
                      actual_missing=[{"category": "timing", "description": "..."}],
                      bucket="missing-info-trap"),
        ]
        result = compute_missing_category_mismatches(generated)

        assert result["total_requirements_with_expected"] == 1
        assert result["total_exact_matches"] == 0
        assert result["total_mismatches"] == 1
        assert len(result["mismatches"]) == 1

    def test_detects_exact_match(self):
        generated = [
            _make_req("REQ-001",
                      expected_missing=["timing"],
                      actual_missing=[{"category": "timing", "description": "..."}]),
        ]
        result = compute_missing_category_mismatches(generated)

        assert result["total_exact_matches"] == 1
        assert result["total_mismatches"] == 0

    def test_ignores_empty_category_strings(self):
        generated = [
            _make_req("REQ-001",
                      expected_missing=["timing"],
                      actual_missing=[
                          {"category": "timing", "description": "..."},
                          {"category": "", "description": "empty"},
                      ]),
        ]
        result = compute_missing_category_mismatches(generated)
        assert result["total_exact_matches"] == 1

    def test_skips_reqs_without_expected_missing(self):
        generated = [
            _make_req("REQ-001", expected_missing=[],
                      actual_missing=[{"category": "timing", "description": "..."}]),
        ]
        result = compute_missing_category_mismatches(generated)
        assert result["total_requirements_with_expected"] == 0

    def test_groups_mismatches_by_bucket(self):
        generated = [
            _make_req("REQ-001",
                      expected_missing=["timing", "threshold"],
                      actual_missing=[],
                      bucket="missing-info-trap"),
            _make_req("REQ-002",
                      expected_missing=["state"],
                      actual_missing=[{"category": "observation", "description": "..."}],
                      bucket="missing-info-trap"),
        ]
        result = compute_missing_category_mismatches(generated)
        bucket_data = result["mismatches_by_bucket"]
        assert "missing-info-trap" in bucket_data
        assert bucket_data["missing-info-trap"]["count"] == 2


class TestCaseCountDistribution:
    def test_computes_distribution(self):
        generated = [
            _make_req("REQ-001", [_make_case(f"TC-{i}") for i in range(3)]),
            _make_req("REQ-002", [_make_case(f"TC-{i}") for i in range(6)]),
            _make_req("REQ-003", [_make_case("TC-0")]),
        ]
        result = compute_case_count_distribution(generated)

        assert result["total_cases"] == 10
        assert result["average_cases_per_req"] == pytest.approx(3.3)
        assert len(result["high_count_requirements"]) == 1
        assert result["high_count_requirements"][0]["requirement_key"] == "REQ-002"

    def test_high_case_count_default_threshold(self):
        generated = [
            _make_req("REQ-001", [_make_case(f"TC-{i}") for i in range(5)]),
        ]
        result = compute_case_count_distribution(generated)
        assert len(result["high_count_requirements"]) == 1

    def test_below_threshold_not_flagged(self):
        generated = [
            _make_req("REQ-001", [_make_case(f"TC-{i}") for i in range(4)]),
        ]
        result = compute_case_count_distribution(generated)
        assert len(result["high_count_requirements"]) == 0


class TestGenerateReport:
    def test_includes_all_required_section_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_json(d / "summary.json", _make_summary(2, 4))
            generated = [
                _make_req("REQ-001", [
                    _make_case("TC-01"),
                    _make_case("TC-02", retry_attempts=1),
                ]),
                _make_req("REQ-002", [
                    _make_case("TC-03", passed=False),
                    _make_case("TC-04"),
                ]),
            ]
            _write_json(d / "generated_cases.json", generated)
            hr = _make_hardrule_eval(
                total_cases=4,
                total_passed=2,
                item_fail_counts={"3.2.1": 2, "4.1.1": 1},
                cases=[
                    _make_hr_case("REQ-001", 0, "TC-01"),
                    _make_hr_case("REQ-001", 1, "TC-02"),
                    _make_hr_case("REQ-002", 0, "TC-03", ["3.2.1", "4.1.1"]),
                    _make_hr_case("REQ-002", 1, "TC-04"),
                ],
            )
            _write_json(d / "hardrule_evaluation.json", hr)

            data = load_round(d)
            report = generate_report(data)

            required_headings = [
                "Executive Summary",
                "Run Metrics",
                "Top Failure Clusters",
                "Philosophy Regression Checks",
                "Representative Cases",
                "Prompt Root-Cause Hypotheses",
                "Patch Candidates",
                "Human Review Checklist",
            ]
            for heading in required_headings:
                assert f"## {heading}" in report, f"Missing heading: {heading}"

    def test_handles_missing_deepseek_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_json(d / "summary.json", _make_summary(1, 1))
            _write_json(d / "generated_cases.json", [
                _make_req("REQ-001", [_make_case("TC-01")]),
            ])
            _write_json(d / "hardrule_evaluation.json",
                        _make_hardrule_eval(total_cases=1, total_passed=1,
                                            cases=[_make_hr_case("REQ-001", 0, "TC-01")]))

            data = load_round(d)
            report = generate_report(data)
            assert "not available" in report.lower() or "insufficient data" in report.lower()


class TestCLI:
    def test_writes_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _write_json(d / "summary.json", _make_summary(1, 1))
            _write_json(d / "generated_cases.json", [
                _make_req("REQ-001", [_make_case("TC-01")]),
            ])
            _write_json(d / "hardrule_evaluation.json",
                        _make_hardrule_eval(total_cases=1, total_passed=1,
                                            cases=[_make_hr_case("REQ-001", 0, "TC-01")]))

            output_path = d / "my_report.md"
            # Simulate what main() does
            data = load_round(d)
            report = generate_report(data)
            output_path.write_text(report, encoding="utf-8")

            assert output_path.exists()
            content = output_path.read_text(encoding="utf-8")
            assert "Executive Summary" in content
