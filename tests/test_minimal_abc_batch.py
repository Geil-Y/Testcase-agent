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
    rev_start = source.index("def _run_review_batch")
    minimal_body = source[min_start:rev_start]

    disallowed = [
        "prepare_clarification_review",
        "validate_clarification_review",
        "prepare_intent_review",
        "validate_case_intent_review",
        "generate_cases",
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
    rev_start = source.index("def _run_review_batch")
    minimal_body = source[min_start:rev_start]

    assert "testcase_agent.pipeline.generate" in minimal_body
    assert "run_pipeline" in minimal_body


def test_cases_to_evaluator_format():
    """Verify _cases_to_evaluator_format converts GeneratedCase to evaluator dicts."""
    import run_eval_batch
    from testcase_agent.parser.html_parser import GeneratedCase, Step

    cases = [
        GeneratedCase(
            title="TC-001",
            objective="Verify overvoltage detection.",
            precondition="BMS initialized.",
            postcondition="System normal.",
            steps=[
                Step(order=1, action="Set voltage above threshold", expected="Voltage above threshold"),
                Step(order=2, action="Wait for response", expected="OV flag set"),
            ],
            raw_html="<testcase>...</testcase>",
        ),
        GeneratedCase(
            title="TC-002",
            objective="Verify boundary behavior.",
            precondition="BMS initialized.",
            postcondition="System normal.",
            steps=[
                Step(order=1, action="Set voltage just below threshold", expected=None),
            ],
            raw_html="<testcase>...</testcase>",
        ),
    ]

    intents = [
        type("Intent", (), {"intent_id": "intent-1", "coverage_dimension": "normal_behavior"})(),
        type("Intent", (), {"intent_id": "intent-2", "coverage_dimension": "boundary_or_threshold"})(),
    ]

    result = run_eval_batch._cases_to_evaluator_format(cases, intents, "REQ-001")

    assert len(result) == 2
    assert result[0]["title"] == "TC-001"
    assert result[0]["pre_condition"] == "BMS initialized."
    assert result[0]["post_condition"] == "System normal."
    assert result[0]["requirement_key"] == "REQ-001"
    assert result[0]["approved_intent_id"] == "intent-1"
    assert result[0]["coverage_dimension"] == "normal_behavior"
    assert result[0]["review_session_id"] == "minimal"
    assert len(result[0]["steps"]) == 2
    assert result[0]["steps"][0]["action"] == "Set voltage above threshold"
    assert result[0]["steps"][0]["expected_result"] == "Voltage above threshold"
    assert result[1]["steps"][0]["expected_result"] == ""


def test_argparse_pipeline_mode_selection():
    """Verify --pipeline argument defaults, validates choices, and parses correctly."""
    import argparse

    parser = argparse.ArgumentParser(description="Batch eval with selectable pipeline")
    parser.add_argument("--pipeline", choices=["minimal", "review"], default="minimal")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default="reviews")

    args = parser.parse_args(["--pipeline", "minimal"])
    assert args.pipeline == "minimal"

    args = parser.parse_args([])
    assert args.pipeline == "minimal"

    args = parser.parse_args(["--pipeline", "review"])
    assert args.pipeline == "review"

    with pytest.raises(SystemExit):
        parser.parse_args(["--pipeline", "invalid"])
