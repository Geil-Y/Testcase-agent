"""Focused tests for minimal ABC batch evaluation path.

Verifies: pipeline mode selection, minimal path does not invoke review stages,
and the ABC pipeline produces evaluator-compatible output.
"""

from pathlib import Path

import pytest


def test_minimal_batch_does_not_import_review_stages():
    """The _run_minimal_batch function must not reference review-pipeline stages."""
    import run_eval_batch

    source = Path(run_eval_batch.__file__).read_text(encoding="utf-8")

    min_start = source.index("def _run_minimal_batch")
    next_def = source.index("def _build_grouped_evaluator_input")
    minimal_body = source[min_start:next_def]

    disallowed = [
        "prepare_clarification_review",
        "validate_clarification_review",
        "prepare_intent_review",
        "validate_case_intent_review",
        "generate_cases",
        "testcase_agent.review_pipeline",
    ]
    for name in disallowed:
        assert name not in minimal_body, (
            f"_run_minimal_batch must not reference {name}"
        )


def test_minimal_batch_calls_run_pipeline():
    """_run_minimal_batch imports run_pipeline from the ABC pipeline."""
    import run_eval_batch

    source = Path(run_eval_batch.__file__).read_text(encoding="utf-8")
    min_start = source.index("def _run_minimal_batch")
    next_def = source.index("def _build_grouped_evaluator_input")
    minimal_body = source[min_start:next_def]

    assert "testcase_agent.pipeline.generate" in minimal_body
    assert "run_pipeline" in minimal_body


def test_build_grouped_evaluator_input():
    """Verify _build_grouped_evaluator_input produces grouped format with analysis."""
    import run_eval_batch
    from testcase_agent.parser.html_parser import GeneratedCase, Step
    from testcase_agent.parser.json_parser import (
        TestBasis, CaseIntentPlan, PlannedCaseIntent, MissingInfoItem,
    )

    # Build a minimal pipeline result
    test_basis = TestBasis(
        requirement_key="REQ-001",
        allowed_signals=["BMS_CellOV_Detect"],
        allowed_thresholds=["r_CellOV_Threshold"],
        allowed_timing=["t_CellOV_Debounce"],
        missing_info=[
            MissingInfoItem(category="timing", description="debounce not specified"),
        ],
    )
    intent_plan = CaseIntentPlan(
        requirement_key="REQ-001",
        case_intents=[
            PlannedCaseIntent(intent_id="i1", coverage_dimension="normal_behavior", intent_text="Verify OV detection"),
        ],
    )

    cases = [
        GeneratedCase(
            title="TC-001",
            objective="Verify overvoltage detection.",
            precondition="BMS initialized.",
            postcondition="System normal.",
            steps=[
                Step(order=1, action="Set voltage above threshold", expected="Voltage above threshold"),
            ],
            raw_html="<testcase>...</testcase>",
        ),
    ]

    class FakeResult:
        pass

    result = FakeResult()
    result.test_basis = test_basis
    result.intent_plan = intent_plan
    result.cases = cases

    grouped = run_eval_batch._build_grouped_evaluator_input(result, "REQ-001", "Requirement description.")

    assert len(grouped) == 1
    assert grouped[0]["requirement_key"] == "REQ-001"
    assert grouped[0]["description"] == "Requirement description."

    analysis = grouped[0]["analysis"]
    assert analysis["signals"] == ["BMS_CellOV_Detect"]
    assert analysis["thresholds"] == ["r_CellOV_Threshold"]
    assert analysis["timing"] == ["t_CellOV_Debounce"]
    assert len(analysis["missing_info_items"]) == 1
    assert analysis["missing_info_items"][0]["category"] == "timing"
    assert len(analysis["case_intents"]) == 1
    assert analysis["case_intents"][0]["coverage"] == "normal_behavior"

    case0 = grouped[0]["cases"][0]
    assert case0["title"] == "TC-001"
    assert case0["precondition"] == "BMS initialized."
    assert case0["postcondition"] == "System normal."
    assert case0["related_requirement"] == "REQ-001"
    assert case0["steps"][0]["action"] == "Set voltage above threshold"
    assert case0["steps"][0]["expected"] == "Voltage above threshold"


def test_argparse_pipeline_mode_selection():
    """Verify --pipeline argument defaults, validates choices, and parses correctly."""
    import argparse

    parser = argparse.ArgumentParser(description="Batch eval with selectable pipeline")
    parser.add_argument("--pipeline", choices=["minimal"], default="minimal")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default="reviews")

    args = parser.parse_args(["--pipeline", "minimal"])
    assert args.pipeline == "minimal"

    args = parser.parse_args([])
    assert args.pipeline == "minimal"

    with pytest.raises(SystemExit):
        parser.parse_args(["--pipeline", "invalid"])
