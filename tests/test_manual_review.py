"""Tests for manual review score loading, weighted calculation, hard gates, and rendering."""

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))

from optimization.manual_review import (
    ReviewEntry,
    compute_weighted_score,
    apply_hard_gates,
    load_review_scores,
    get_review_summary,
    HardGateResult,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _review_json(entries: list[dict]) -> str:
    return json.dumps(entries, ensure_ascii=False, indent=2)


def _entry_dict(requirement_key="REQ-001", case_index=0, **scores) -> dict:
    defaults = {
        "executability": 4,
        "observability": 4,
        "coverage_value": 4,
        "missing_information_detection": 4,
    }
    defaults.update(scores)
    return {"requirement_key": requirement_key, "case_index": case_index, **defaults}


def _case(**overrides) -> dict:
    defaults = {
        "title": "TC-01",
        "steps": [
            {"order": 1, "action": "Set voltage", "expected": "Flag set"},
        ],
    }
    defaults.update(overrides)
    return defaults


def _gen_data(entries: list[dict]) -> list[dict]:
    return [
        {
            "requirement_key": e["requirement_key"],
            "expected_missing_categories": e.get("expected_missing_categories", []),
            "cases": e.get("cases", []),
        }
        for e in entries
    ]


# ── Compute weighted score ──────────────────────────────────────────────


class TestWeightedScore:
    def test_perfect_scores(self):
        entry = ReviewEntry("R1", 0, 5, 5, 5, 5)
        assert compute_weighted_score(entry) == 5.0

    def test_minimum_scores(self):
        entry = ReviewEntry("R1", 0, 1, 1, 1, 1)
        assert compute_weighted_score(entry) == 1.0

    def test_mixed_scores(self):
        entry = ReviewEntry("R1", 0,
            executability=3,
            observability=4,
            coverage_value=5,
            missing_information_detection=2,
        )
        expected = 0.20 * 3 + 0.20 * 4 + 0.20 * 5 + 0.40 * 2  # = 3.2
        assert compute_weighted_score(entry) == pytest.approx(expected, abs=0.05)


# ── Hard gates ────────────────────────────────────────────────────────────


class TestHardGates:
    def test_missing_info_detection_below_3_unacceptable(self):
        entry = ReviewEntry("R1", 0, 5, 5, 5, 2)
        g = apply_hard_gates(entry)
        assert g.unacceptable is True
        assert any("missing_information_detection=2" in r for r in g.reasons)

    def test_missing_info_detection_3_acceptable(self):
        entry = ReviewEntry("R1", 0, 4, 4, 4, 3)
        g = apply_hard_gates(entry)
        assert g.unacceptable is False

    def test_expected_missing_but_no_nr_in_case(self):
        entry = ReviewEntry("R1", 0, 4, 4, 4, 5)
        case = _case(steps=[_step("Set voltage to threshold", "OK")])
        g = apply_hard_gates(entry, case, expected_missing_categories=["timing"])
        assert g.unacceptable is True
        assert any("lacks [NEEDS REVIEW]" in r for r in g.reasons)

    def test_expected_missing_and_nr_in_case_passes(self):
        entry = ReviewEntry("R1", 0, 4, 4, 4, 4)
        case = _case(steps=[_step("Wait [NEEDS REVIEW] ms", None)])
        g = apply_hard_gates(entry, case, expected_missing_categories=["timing"])
        assert g.unacceptable is False

    def test_invented_numeric_when_threshold_missing(self):
        entry = ReviewEntry("R1", 0, 4, 4, 4, 5)
        case = _case(steps=[_step("Set to 4.2V", "Flag set")])
        g = apply_hard_gates(entry, case, expected_missing_categories=["threshold"])
        assert g.unacceptable is True
        assert any("invent" in r.lower() for r in g.reasons)

    def test_unnecessary_nr_is_warning_not_severe(self):
        entry = ReviewEntry("R1", 0, 5, 5, 5, 5)
        case = _case(steps=[_step("Set [NEEDS REVIEW] value", "OK")])
        g = apply_hard_gates(entry, case, expected_missing_categories=[])
        assert g.unacceptable is False
        assert len(g.warnings) >= 1
        assert any("unnecessary" in w.lower() or "penalized" in w.lower() for w in g.warnings)

    def test_no_case_data_no_case_gates(self):
        """Gates 2-4 are skipped when no case dict is provided."""
        entry = ReviewEntry("R1", 0, 4, 4, 4, 4)
        g = apply_hard_gates(entry, None, expected_missing_categories=["timing"])
        # Only gate 1 checked (missing_info_detection >= 3, so no issue)
        assert g.unacceptable is False


# ── Load and validate review file ───────────────────────────────────────


class TestLoadReviewScores:
    def test_loads_valid_file(self, tmp_path):
        p = tmp_path / "reviews.json"
        p.write_text(_review_json([_entry_dict("R1", 0)]), encoding="utf-8")
        entries = load_review_scores(str(p))
        assert len(entries) == 1
        assert entries[0].requirement_key == "R1"
        assert entries[0].executability == 4

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            load_review_scores(str(tmp_path / "nonexistent.json"))

    def test_invalid_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{invalid", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid JSON"):
            load_review_scores(str(p))

    def test_not_a_list_raises(self, tmp_path):
        p = tmp_path / "obj.json"
        p.write_text('{"key": "value"}', encoding="utf-8")
        with pytest.raises(ValueError, match="JSON array"):
            load_review_scores(str(p))

    def test_missing_requirement_key_raises(self, tmp_path):
        p = tmp_path / "reviews.json"
        p.write_text(_review_json([{"case_index": 0, "executability": 3, "observability": 3, "coverage_value": 3, "missing_information_detection": 3}]), encoding="utf-8")
        with pytest.raises(ValueError, match="requirement_key"):
            load_review_scores(str(p))

    def test_score_out_of_range_raises(self, tmp_path):
        p = tmp_path / "reviews.json"
        p.write_text(_review_json([_entry_dict("R1", 0, executability=6)]), encoding="utf-8")
        with pytest.raises(ValueError, match="executability"):
            load_review_scores(str(p))

    def test_score_0_raises(self, tmp_path):
        p = tmp_path / "reviews.json"
        p.write_text(_review_json([_entry_dict("R1", 0, observability=0)]), encoding="utf-8")
        with pytest.raises(ValueError, match="observability"):
            load_review_scores(str(p))

    def test_negative_case_index_raises(self, tmp_path):
        p = tmp_path / "reviews.json"
        p.write_text(_review_json([_entry_dict("R1", -1)]), encoding="utf-8")
        with pytest.raises(ValueError, match="case_index"):
            load_review_scores(str(p))

    def test_optional_fields(self, tmp_path):
        p = tmp_path / "reviews.json"
        data = [_entry_dict("R1", 0)]
        data[0]["reviewer"] = "Alice"
        data[0]["notes"] = "Looks good"
        p.write_text(_review_json(data), encoding="utf-8")
        entries = load_review_scores(str(p))
        assert entries[0].reviewer == "Alice"
        assert entries[0].notes == "Looks good"


# ── Review summary ─────────────────────────────────────────────────────


class TestGetReviewSummary:
    def test_average_weighted_score(self):
        entries = [
            ReviewEntry("R1", 0, 5, 5, 5, 5),
            ReviewEntry("R2", 0, 1, 1, 1, 1),
        ]
        gen = _gen_data([
            {"requirement_key": "R1", "expected_missing_categories": [], "cases": [_case()]},
            {"requirement_key": "R2", "expected_missing_categories": [], "cases": [_case()]},
        ])
        s = get_review_summary(entries, gen)
        assert s["average_weighted_score"] == 3.0
        assert s["total_entries"] == 2

    def test_unacceptable_count(self):
        entries = [ReviewEntry("R1", 0, 5, 5, 5, 2)]
        gen = _gen_data([
            {"requirement_key": "R1", "expected_missing_categories": [], "cases": [_case()]},
        ])
        s = get_review_summary(entries, gen)
        assert s["total_unacceptable"] == 1
        assert len(s["unacceptable"]) == 1

    def test_dimension_averages(self):
        entries = [
            ReviewEntry("R1", 0, 5, 1, 5, 1),
            ReviewEntry("R2", 0, 3, 3, 3, 3),
        ]
        gen = _gen_data([
            {"requirement_key": "R1", "expected_missing_categories": [], "cases": [_case()]},
            {"requirement_key": "R2", "expected_missing_categories": [], "cases": [_case()]},
        ])
        s = get_review_summary(entries, gen)
        assert s["dimension_averages"]["executability"] == 4.0  # (5+3)/2
        assert s["dimension_averages"]["observability"] == 2.0  # (1+3)/2

    def test_score_distribution(self):
        entries = [ReviewEntry("R1", 0, 5, 5, 5, 5)]  # 5.0
        gen = _gen_data([
            {"requirement_key": "R1", "expected_missing_categories": [], "cases": [_case()]},
        ])
        s = get_review_summary(entries, gen)
        assert s["score_distribution"]["4-5"] == 1

    def test_empty_entries_returns_empty(self):
        assert get_review_summary([], []) == {}

    def test_requirement_key_not_found_raises(self):
        entries = [ReviewEntry("MISSING", 0, 4, 4, 4, 4)]
        gen = _gen_data([
            {"requirement_key": "R1", "expected_missing_categories": [], "cases": [_case()]},
        ])
        with pytest.raises(ValueError, match="MISSING"):
            get_review_summary(entries, gen)

    def test_case_index_out_of_range_raises(self):
        entries = [ReviewEntry("R1", 5, 4, 4, 4, 4)]
        gen = _gen_data([
            {"requirement_key": "R1", "expected_missing_categories": [], "cases": [_case(), _case()]},
        ])
        with pytest.raises(ValueError, match="case_index=5"):
            get_review_summary(entries, gen)

    def test_case_index_0_when_no_cases_raises(self):
        entries = [ReviewEntry("R1", 0, 4, 4, 4, 4)]
        gen = _gen_data([
            {"requirement_key": "R1", "expected_missing_categories": [], "cases": []},
        ])
        with pytest.raises(ValueError, match="case_index=0"):
            get_review_summary(entries, gen)


# ── Rendering in report ────────────────────────────────────────────────


class TestManualReviewSectionRendering:
    def test_section_present_with_review_data(self):
        """Report HTML includes Manual Review Scores when data is available."""
        from optimization.generate_report import _render_manual_review_section

        summary = {
            "average_weighted_score": 4.2,
            "dimension_averages": {
                "executability": 4.5,
                "observability": 4.0,
                "coverage_value": 4.3,
                "missing_information_detection": 4.0,
            },
            "unacceptable": [],
            "score_distribution": {"4-5": 5, "3-4": 0, "2-3": 0, "1-2": 0, "0-1": 0},
            "entry_details": [
                {
                    "requirement_key": "R1",
                    "case_title": "TC-01",
                    "executability": 5, "observability": 4,
                    "coverage_value": 4, "missing_information_detection": 4,
                    "weighted_score": 4.2, "unacceptable": False,
                    "unacceptable_reasons": [], "warnings": [],
                    "reviewer": "", "notes": "",
                }
            ],
            "total_entries": 1,
            "total_unacceptable": 0,
        }
        html = _render_manual_review_section(summary)
        assert "Manual Review Scores" in html
        assert "4.2" in html
        assert "R1" in html

    def test_section_absent_when_no_data(self):
        from optimization.generate_report import _render_manual_review_section
        assert _render_manual_review_section({}) == ""

    def test_section_shows_error_on_load_failure(self):
        from optimization.generate_report import _render_manual_review_section
        html = _render_manual_review_section({"_error": "bad JSON"})
        assert "加载 review 文件失败" in html
        assert "bad JSON" in html

    def test_section_shows_unacceptable_case(self):
        from optimization.generate_report import _render_manual_review_section

        summary = {
            "average_weighted_score": 3.5,
            "dimension_averages": {"executability": 4, "observability": 4, "coverage_value": 4, "missing_information_detection": 2},
            "unacceptable": [{
                "requirement_key": "R1",
                "case_title": "Bad case",
                "unacceptable_reasons": ["missing_information_detection=2 (< 3)"],
            }],
            "score_distribution": {"2-3": 1},
            "entry_details": [{
                "requirement_key": "R1", "case_title": "Bad case",
                "executability": 4, "observability": 4,
                "coverage_value": 4, "missing_information_detection": 2,
                "weighted_score": 3.2, "unacceptable": True,
                "unacceptable_reasons": ["missing_information_detection=2 (< 3)"],
                "warnings": [], "reviewer": "", "notes": "",
            }],
            "total_entries": 1,
            "total_unacceptable": 1,
        }
        html = _render_manual_review_section(summary)
        assert "Unacceptable Cases" in html
        assert "R1" in html
        assert "❌" in html

    def test_report_without_review_file_has_no_manual_review_section(self):
        """When manual_review_scores.json is absent, the section is empty."""
        # No file → review_summary stays empty {} → _render returns ""
        from optimization.generate_report import _render_manual_review_section
        assert _render_manual_review_section({}) == ""
        assert _render_manual_review_section({}) == ""  # not None, empty string


def _step(action="Do something", expected="OK"):
    return {"order": 1, "action": action, "expected": expected}
