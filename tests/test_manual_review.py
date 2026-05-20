"""Tests for 8-dimension manual review loading, weighting, hard gates, and rendering."""

import json

import pytest

from optimization.manual_review import (
    ReviewCaseEntry,
    ReviewRequirementEntry,
    apply_hard_gates,
    compute_weighted_score,
    get_review_summary,
    load_review_scores,
)


# -- Helpers ---------------------------------------------------------------

def _review_json(entries: list[dict] | dict) -> str:
    return json.dumps(entries, ensure_ascii=False, indent=2)


def _case_scores(**overrides) -> dict:
    defaults = {
        "case_index": 0,
        "requirement_alignment": 4,
        "executability": 4,
        "observability": 4,
        "pass_fail_clarity": 4,
        "information_integrity": 4,
        "state_and_environment_control": 4,
        "automation_readiness": 4,
    }
    defaults.update(overrides)
    return defaults


def _entry_dict(requirement_key="REQ-001", **overrides) -> dict:
    defaults = {
        "requirement_key": requirement_key,
        "coverage_value": 4,
        "cases": [_case_scores()],
    }
    defaults.update(overrides)
    return defaults


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


def _review_case(requirement_key="R1", case_index=0, **scores) -> ReviewCaseEntry:
    defaults = {
        "requirement_alignment": 4,
        "executability": 4,
        "observability": 4,
        "pass_fail_clarity": 4,
        "information_integrity": 4,
        "state_and_environment_control": 4,
        "automation_readiness": 4,
    }
    defaults.update(scores)
    return ReviewCaseEntry(requirement_key, case_index, **defaults)


def _review_requirement(requirement_key="R1", coverage_value=4, cases=None) -> ReviewRequirementEntry:
    return ReviewRequirementEntry(
        requirement_key=requirement_key,
        coverage_value=coverage_value,
        cases=cases if cases is not None else [_review_case(requirement_key)],
    )


def _step(action="Do something", expected="OK"):
    return {"order": 1, "action": action, "expected": expected}


# -- Compute weighted score ------------------------------------------------

class TestWeightedScore:
    def test_perfect_scores(self):
        entry = _review_requirement(
            coverage_value=5,
            cases=[_review_case(requirement_alignment=5, executability=5, observability=5,
                                pass_fail_clarity=5, information_integrity=5,
                                state_and_environment_control=5, automation_readiness=5)],
        )
        assert compute_weighted_score(entry) == 5.0

    def test_minimum_scores(self):
        entry = _review_requirement(
            coverage_value=1,
            cases=[_review_case(requirement_alignment=1, executability=1, observability=1,
                                pass_fail_clarity=1, information_integrity=1,
                                state_and_environment_control=1, automation_readiness=1)],
        )
        assert compute_weighted_score(entry) == 1.0

    def test_mixed_scores_uses_new_weights_and_case_average(self):
        entry = _review_requirement(
            coverage_value=3,
            cases=[
                _review_case(requirement_alignment=5, information_integrity=5, executability=4,
                             observability=4, pass_fail_clarity=3,
                             state_and_environment_control=3, automation_readiness=3),
                _review_case("R1", 1, requirement_alignment=3, information_integrity=3, executability=2,
                             observability=2, pass_fail_clarity=3,
                             state_and_environment_control=3, automation_readiness=3),
            ],
        )
        expected = (
            0.20 * 4
            + 0.20 * 4
            + 0.15 * 3
            + 0.15 * 3
            + 0.10 * 3
            + 0.10 * 3
            + 0.05 * 3
            + 0.05 * 3
        )
        assert compute_weighted_score(entry) == pytest.approx(expected, abs=0.05)


# -- Hard gates ------------------------------------------------------------

class TestHardGates:
    def test_information_integrity_below_3_unacceptable(self):
        entry = _review_case(information_integrity=2)
        g = apply_hard_gates(entry)
        assert g.unacceptable is True
        assert any("information_integrity=2" in r for r in g.reasons)

    def test_information_integrity_3_acceptable(self):
        entry = _review_case(information_integrity=3)
        g = apply_hard_gates(entry)
        assert g.unacceptable is False

    def test_expected_missing_but_no_nr_in_case(self):
        entry = _review_case(information_integrity=5)
        case = _case(steps=[_step("Set voltage to threshold", "OK")])
        g = apply_hard_gates(entry, case, expected_missing_categories=["timing"])
        assert g.unacceptable is True
        assert any("lacks [NEEDS REVIEW]" in r for r in g.reasons)

    def test_expected_missing_and_nr_in_case_passes(self):
        entry = _review_case(information_integrity=4)
        case = _case(steps=[_step("Wait [NEEDS REVIEW] ms", None)])
        g = apply_hard_gates(entry, case, expected_missing_categories=["timing"])
        assert g.unacceptable is False

    def test_invented_numeric_when_threshold_missing(self):
        entry = _review_case(information_integrity=5)
        case = _case(steps=[_step("Set to 4.2V", "Flag set")])
        g = apply_hard_gates(entry, case, expected_missing_categories=["threshold"])
        assert g.unacceptable is True
        assert any("invent" in r.lower() for r in g.reasons)

    def test_unnecessary_nr_is_warning_not_severe(self):
        entry = _review_case(information_integrity=5)
        case = _case(steps=[_step("Set [NEEDS REVIEW] value", "OK")])
        g = apply_hard_gates(entry, case, expected_missing_categories=[])
        assert g.unacceptable is False
        assert len(g.warnings) >= 1
        assert any("unnecessary" in w.lower() or "penalized" in w.lower() for w in g.warnings)


# -- Load and validate review file ----------------------------------------

class TestLoadReviewScores:
    def test_loads_valid_object_file(self, tmp_path):
        p = tmp_path / "reviews.json"
        p.write_text(_review_json({"requirements": [_entry_dict("R1")]}), encoding="utf-8")
        entries = load_review_scores(str(p))
        assert len(entries) == 1
        assert entries[0].requirement_key == "R1"
        assert entries[0].coverage_value == 4
        assert entries[0].cases[0].executability == 4

    def test_loads_valid_array_file(self, tmp_path):
        p = tmp_path / "reviews.json"
        p.write_text(_review_json([_entry_dict("R1")]), encoding="utf-8")
        entries = load_review_scores(str(p))
        assert len(entries) == 1

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(ValueError, match="not found"):
            load_review_scores(str(tmp_path / "nonexistent.json"))

    def test_invalid_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{invalid", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid JSON"):
            load_review_scores(str(p))

    def test_not_a_list_or_object_requirements_raises(self, tmp_path):
        p = tmp_path / "obj.json"
        p.write_text('{"key": "value"}', encoding="utf-8")
        with pytest.raises(ValueError, match="requirements"):
            load_review_scores(str(p))

    def test_legacy_flat_entry_raises_clear_error(self, tmp_path):
        p = tmp_path / "reviews.json"
        p.write_text(_review_json([{"requirement_key": "R1", "case_index": 0}]), encoding="utf-8")
        with pytest.raises(ValueError, match="8-dimension"):
            load_review_scores(str(p))

    def test_score_out_of_range_raises(self, tmp_path):
        p = tmp_path / "reviews.json"
        p.write_text(_review_json([_entry_dict("R1", cases=[_case_scores(executability=6)])]), encoding="utf-8")
        with pytest.raises(ValueError, match="executability"):
            load_review_scores(str(p))

    def test_negative_case_index_raises(self, tmp_path):
        p = tmp_path / "reviews.json"
        p.write_text(_review_json([_entry_dict("R1", cases=[_case_scores(case_index=-1)])]), encoding="utf-8")
        with pytest.raises(ValueError, match="case_index"):
            load_review_scores(str(p))


# -- Review summary --------------------------------------------------------

class TestGetReviewSummary:
    def test_average_weighted_score_is_requirement_average(self):
        entries = [
            _review_requirement("R1", coverage_value=5, cases=[
                _review_case("R1", requirement_alignment=5, executability=5, observability=5,
                             pass_fail_clarity=5, information_integrity=5,
                             state_and_environment_control=5, automation_readiness=5),
                _review_case("R1", 1, requirement_alignment=5, executability=5, observability=5,
                             pass_fail_clarity=5, information_integrity=5,
                             state_and_environment_control=5, automation_readiness=5),
            ]),
            _review_requirement("R2", coverage_value=1, cases=[
                _review_case("R2", requirement_alignment=1, executability=1, observability=1,
                             pass_fail_clarity=1, information_integrity=1,
                             state_and_environment_control=1, automation_readiness=1),
            ]),
        ]
        gen = _gen_data([
            {"requirement_key": "R1", "expected_missing_categories": [], "cases": [_case(), _case()]},
            {"requirement_key": "R2", "expected_missing_categories": [], "cases": [_case()]},
        ])
        s = get_review_summary(entries, gen)
        assert s["average_weighted_score"] == 3.0
        assert s["total_requirements"] == 2
        assert s["total_cases"] == 3

    def test_unacceptable_count(self):
        entries = [_review_requirement("R1", cases=[_review_case("R1", information_integrity=2)])]
        gen = _gen_data([
            {"requirement_key": "R1", "expected_missing_categories": [], "cases": [_case()]},
        ])
        s = get_review_summary(entries, gen)
        assert s["total_unacceptable"] == 1
        assert len(s["unacceptable"]) == 1

    def test_dimension_averages_and_mins(self):
        entries = [
            _review_requirement("R1", coverage_value=5, cases=[
                _review_case("R1", requirement_alignment=5, observability=1),
                _review_case("R1", 1, requirement_alignment=3, observability=3),
            ]),
            _review_requirement("R2", coverage_value=3, cases=[
                _review_case("R2", requirement_alignment=3, observability=3),
            ]),
        ]
        gen = _gen_data([
            {"requirement_key": "R1", "expected_missing_categories": [], "cases": [_case(), _case()]},
            {"requirement_key": "R2", "expected_missing_categories": [], "cases": [_case()]},
        ])
        s = get_review_summary(entries, gen)
        assert s["dimension_averages"]["coverage_value"] == 4.0
        assert s["dimension_averages"]["requirement_alignment"] == 3.5
        assert s["dimension_averages"]["observability"] == 2.5
        assert s["dimension_mins"]["observability"] == 1

    def test_score_distribution(self):
        entries = [_review_requirement("R1", coverage_value=5, cases=[
            _review_case("R1", requirement_alignment=5, executability=5, observability=5,
                         pass_fail_clarity=5, information_integrity=5,
                         state_and_environment_control=5, automation_readiness=5)
        ])]
        gen = _gen_data([
            {"requirement_key": "R1", "expected_missing_categories": [], "cases": [_case()]},
        ])
        s = get_review_summary(entries, gen)
        assert s["score_distribution"]["4-5"] == 1

    def test_empty_entries_returns_empty(self):
        assert get_review_summary([], []) == {}

    def test_requirement_key_not_found_raises(self):
        entries = [_review_requirement("MISSING")]
        gen = _gen_data([
            {"requirement_key": "R1", "expected_missing_categories": [], "cases": [_case()]},
        ])
        with pytest.raises(ValueError, match="MISSING"):
            get_review_summary(entries, gen)

    def test_case_index_out_of_range_raises(self):
        entries = [_review_requirement("R1", cases=[_review_case("R1", 5)])]
        gen = _gen_data([
            {"requirement_key": "R1", "expected_missing_categories": [], "cases": [_case(), _case()]},
        ])
        with pytest.raises(ValueError, match="case_index=5"):
            get_review_summary(entries, gen)


# -- Rendering in report --------------------------------------------------

class TestManualReviewSectionRendering:
    def test_section_present_with_review_data(self):
        from optimization.generate_report import _render_manual_review_section

        summary = {
            "average_weighted_score": 4.2,
            "dimension_averages": {
                "requirement_alignment": 4.5,
                "information_integrity": 4.0,
                "executability": 4.5,
                "observability": 4.0,
                "pass_fail_clarity": 4.0,
                "coverage_value": 4.0,
                "state_and_environment_control": 4.0,
                "automation_readiness": 4.0,
            },
            "dimension_mins": {
                "requirement_alignment": 4,
                "information_integrity": 4,
                "executability": 4,
                "observability": 4,
                "pass_fail_clarity": 4,
                "coverage_value": 4,
                "state_and_environment_control": 4,
                "automation_readiness": 4,
            },
            "unacceptable": [],
            "score_distribution": {"4-5": 1, "3-4": 0, "2-3": 0, "1-2": 0, "0-1": 0},
            "entry_details": [
                {
                    "requirement_key": "R1",
                    "case_title": "TC-01",
                    "requirement_alignment": 5,
                    "information_integrity": 4,
                    "executability": 4,
                    "observability": 4,
                    "pass_fail_clarity": 4,
                    "coverage_value": 4,
                    "state_and_environment_control": 4,
                    "automation_readiness": 4,
                    "requirement_weighted_score": 4.2,
                    "unacceptable": False,
                    "unacceptable_reasons": [],
                    "warnings": [],
                    "reviewer": "",
                    "notes": "",
                }
            ],
            "total_requirements": 1,
            "total_cases": 1,
            "total_entries": 1,
            "total_unacceptable": 0,
        }
        html = _render_manual_review_section(summary)
        assert "Manual Review Scores" in html
        assert "Requirement Alignment" in html
        assert "Information Integrity" in html
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
            "dimension_averages": {"information_integrity": 2},
            "dimension_mins": {"information_integrity": 2},
            "unacceptable": [{
                "requirement_key": "R1",
                "case_title": "Bad case",
                "unacceptable_reasons": ["information_integrity=2 (< 3)"],
            }],
            "score_distribution": {"2-3": 1},
            "entry_details": [{
                "requirement_key": "R1",
                "case_title": "Bad case",
                "requirement_alignment": 4,
                "information_integrity": 2,
                "executability": 4,
                "observability": 4,
                "pass_fail_clarity": 4,
                "coverage_value": 4,
                "state_and_environment_control": 4,
                "automation_readiness": 4,
                "requirement_weighted_score": 3.2,
                "unacceptable": True,
                "unacceptable_reasons": ["information_integrity=2 (< 3)"],
                "warnings": [],
                "reviewer": "",
                "notes": "",
            }],
            "total_requirements": 1,
            "total_cases": 1,
            "total_entries": 1,
            "total_unacceptable": 1,
        }
        html = _render_manual_review_section(summary)
        assert "Unacceptable Cases" in html
        assert "R1" in html
        assert "❌" in html
