"""Tests for requirement set loading, validation, and selection."""

from pathlib import Path

import pytest

from optimization.cli import (
    load_requirement_set,
    select_by_requirement_set,
    validate_requirement_set,
)
from testcase_agent.review_pipeline.artifacts.models import RequirementInput

_PROJECT_ROOT = Path(__file__).resolve().parents[1]


# ── Shared fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def prompt_eval_v1_path() -> Path:
    p = _PROJECT_ROOT / "optimization_runs" / "requirement_sets" / "prompt_eval_v1.json"
    assert p.exists(), f"Expected set file not found: {p}"
    return p


def _make_inputs(keys: list[str]) -> list[RequirementInput]:
    return [
        RequirementInput(requirement_key=k, description=f"Desc for {k}")
        for k in keys
    ]


def _valid_set(entries: list[dict]) -> dict:
    return {"name": "Test Set", "entries": entries}


def _entry(key: str, bucket: str = "test", cats: list[str] | None = None) -> dict:
    return {
        "requirement_key": key,
        "evaluation_bucket": bucket,
        "expected_missing_categories": cats if cats is not None else [],
        "rationale": "test rationale",
        "description": "Test requirement description for " + key,
    }


# ── Load and validate ───────────────────────────────────────────────────


class TestLoadPromptEvalV1:
    def test_loads_entries(self, prompt_eval_v1_path):
        data = load_requirement_set(str(prompt_eval_v1_path))
        assert data["name"] == "Prompt Evaluation Set V1"
        assert len(data["entries"]) > 0

    def test_no_duplicate_keys(self, prompt_eval_v1_path):
        data = load_requirement_set(str(prompt_eval_v1_path))
        keys = [e["requirement_key"] for e in data["entries"]]
        assert len(keys) == len(set(keys))

    def test_all_categories_valid(self, prompt_eval_v1_path):
        data = load_requirement_set(str(prompt_eval_v1_path))
        valid = {"signal", "threshold", "timing", "state", "observation"}
        for e in data["entries"]:
            for c in e["expected_missing_categories"]:
                assert c in valid, f"Invalid category '{c}' for {e['requirement_key']}"

    def test_all_entries_have_required_fields(self, prompt_eval_v1_path):
        data = load_requirement_set(str(prompt_eval_v1_path))
        for e in data["entries"]:
            assert isinstance(e["requirement_key"], str) and e["requirement_key"]
            assert isinstance(e["evaluation_bucket"], str) and e["evaluation_bucket"]
            assert isinstance(e["expected_missing_categories"], list)
            assert isinstance(e["rationale"], str) and e["rationale"]

    def test_expected_missing_category_counts(self, prompt_eval_v1_path):
        """Spot-check known entries from each bucket."""
        data = load_requirement_set(str(prompt_eval_v1_path))
        lookup = {e["requirement_key"]: e for e in data["entries"]}

        # Complete info baseline → no missing
        assert lookup["REQ-BMS-OVP-002"]["expected_missing_categories"] == []
        # Raw OV detection has a symbolic threshold, but still lacks the
        # controllable cell-voltage interface and raw response/sample time.
        assert lookup["REQ-BMS-OVP-001"]["expected_missing_categories"] == ["signal", "timing"]
        # UVP-001 provides the 2.80 V threshold; the missing semantics are the
        # controllable cell-voltage interface, response timing, and concrete
        # evidence/value for discharge limiting.
        assert lookup["REQ-BMS-UVP-001"]["expected_missing_categories"] == ["signal", "timing", "observation"]
        # BAL-002 provides 20 mV and 5 A thresholds; timeout duration and
        # concrete balancing status/control signals and observations remain
        # missing.
        assert lookup["REQ-BMS-BAL-002"]["expected_missing_categories"] == ["signal", "timing", "observation"]
        # Missing info trap → threshold + timing
        assert lookup["REQ-BMS-THM-004"]["expected_missing_categories"] == ["threshold", "timing"]
        # Multi-branch → state + observation
        assert lookup["REQ-BMS-CHG-004"]["expected_missing_categories"] == ["state", "observation"]
        # State/observation/diagnostic → state + timing
        assert lookup["REQ-BMS-STM-006"]["expected_missing_categories"] == ["state", "timing"]


class TestValidateRequirementSet:
    def test_rejects_invalid_category(self):
        data = _valid_set([_entry("R1", cats=["timing", "bad_category"])])
        with pytest.raises(ValueError, match="invalid expected_missing_categories"):
            validate_requirement_set(data, "test.json")

    def test_rejects_duplicate_key(self):
        data = _valid_set([
            _entry("R1"),
            _entry("R2"),
            _entry("R1"),  # duplicate
        ])
        with pytest.raises(ValueError, match="Duplicate requirement_key"):
            validate_requirement_set(data, "test.json")

    def test_rejects_missing_name(self):
        data = {"entries": [_entry("R1")]}
        with pytest.raises(ValueError, match="missing a non-empty 'name'"):
            validate_requirement_set(data, "test.json")

    def test_rejects_empty_entries(self):
        data = {"name": "Empty", "entries": []}
        with pytest.raises(ValueError, match="has no 'entries'"):
            validate_requirement_set(data, "test.json")

    def test_rejects_missing_key(self):
        data = _valid_set([{"evaluation_bucket": "test", "expected_missing_categories": [], "rationale": "x"}])
        with pytest.raises(ValueError, match="missing a valid 'requirement_key'"):
            validate_requirement_set(data, "test.json")

    def test_rejects_non_list_categories(self):
        data = _valid_set([{
            "requirement_key": "R1",
            "evaluation_bucket": "test",
            "expected_missing_categories": "timing",
            "rationale": "x",
        }])
        with pytest.raises(ValueError, match="must be a list"):
            validate_requirement_set(data, "test.json")


class TestLoadRequirementSetErrors:
    def test_missing_file_raises(self):
        with pytest.raises(ValueError, match="not found"):
            load_requirement_set("nonexistent_file.json")

    def test_invalid_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid JSON"):
            load_requirement_set(str(p))


# ── Selection ───────────────────────────────────────────────────────────


class TestSelectByRequirementSet:
    def test_preserves_set_order(self):
        all_inputs = _make_inputs(["C", "A", "B"])
        set_data = _valid_set([_entry("A"), _entry("B"), _entry("C")])
        result = select_by_requirement_set(all_inputs, set_data)
        assert [r.requirement_key for r in result] == ["A", "B", "C"]

    def test_raises_on_missing_key(self):
        all_inputs = _make_inputs(["A", "B"])
        set_data = _valid_set([_entry("A"), _entry("MISSING"), _entry("B")])
        with pytest.raises(ValueError, match="MISSING"):
            select_by_requirement_set(all_inputs, set_data)

    def test_returns_subset(self):
        all_inputs = _make_inputs(["A", "B", "C", "D", "E"])
        set_data = _valid_set([_entry("A"), _entry("C")])
        result = select_by_requirement_set(all_inputs, set_data)
        assert len(result) == 2
        assert [r.requirement_key for r in result] == ["A", "C"]

    def test_empty_set_returns_empty(self):
        all_inputs = _make_inputs(["A", "B"])
        set_data = _valid_set([])
        result = select_by_requirement_set(all_inputs, set_data)
        assert result == []
