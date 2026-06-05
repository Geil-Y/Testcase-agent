"""Tests for the prompt evaluation requirement set artifact."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_VALID_MISSING_CATEGORIES = {"signal", "threshold", "timing", "state", "observation"}


@pytest.fixture
def prompt_eval_v1() -> dict:
    path = _PROJECT_ROOT / "docs" / "quality" / "requirement_sets" / "prompt_eval_v1.json"
    assert path.exists(), f"Expected set file not found: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


class TestPromptEvalV1:
    def test_loads_entries(self, prompt_eval_v1):
        assert prompt_eval_v1["name"] == "Prompt Evaluation Set V1"
        assert len(prompt_eval_v1["entries"]) > 0

    def test_no_duplicate_keys(self, prompt_eval_v1):
        keys = [entry["requirement_key"] for entry in prompt_eval_v1["entries"]]
        assert len(keys) == len(set(keys))

    def test_all_categories_valid(self, prompt_eval_v1):
        for entry in prompt_eval_v1["entries"]:
            for category in entry["expected_missing_categories"]:
                assert category in _VALID_MISSING_CATEGORIES

    def test_all_entries_have_required_fields(self, prompt_eval_v1):
        for entry in prompt_eval_v1["entries"]:
            assert isinstance(entry["requirement_key"], str) and entry["requirement_key"]
            assert isinstance(entry["evaluation_bucket"], str) and entry["evaluation_bucket"]
            assert isinstance(entry["expected_missing_categories"], list)
            assert isinstance(entry["rationale"], str) and entry["rationale"]
            assert isinstance(entry["description"], str) and entry["description"]

    def test_expected_missing_category_counts(self, prompt_eval_v1):
        lookup = {entry["requirement_key"]: entry for entry in prompt_eval_v1["entries"]}

        assert lookup["REQ-BMS-OVP-002"]["expected_missing_categories"] == []
        assert lookup["REQ-BMS-OVP-001"]["expected_missing_categories"] == ["signal", "timing"]
        assert lookup["REQ-BMS-UVP-001"]["expected_missing_categories"] == [
            "signal",
            "timing",
            "observation",
        ]
        assert lookup["REQ-BMS-BAL-002"]["expected_missing_categories"] == [
            "signal",
            "timing",
            "observation",
        ]
        assert lookup["REQ-BMS-THM-004"]["expected_missing_categories"] == ["threshold", "timing"]
        assert lookup["REQ-BMS-CHG-004"]["expected_missing_categories"] == ["state", "observation"]
        assert lookup["REQ-BMS-STM-006"]["expected_missing_categories"] == ["state", "timing"]
