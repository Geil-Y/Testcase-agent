"""CLI entry point for the review pipeline.

Usage: python -m review_pipeline.cli <command> [options]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from review_pipeline.artifacts.io import read_json
from review_pipeline.artifacts.validation import ValidationResult


def _cmd_prepare_clarification_review(args: argparse.Namespace) -> int:
    from review_pipeline.stages.decompose_requirement import prepare_clarification_review
    try:
        provider = None
        if not args.mock:
            from testcase_agent.config import get_settings
            from testcase_agent.provider.factory import create_provider
            provider = create_provider(get_settings())
        review = prepare_clarification_review(args.input, args.out, provider=provider)
        print(f"Clarification review written to {args.out}/clarification_review.json")
        print(f"  Items: {len(review.decomposition.ambiguities)} ambiguities")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_validate_review(args: argparse.Namespace) -> int:
    from review_pipeline.stages.validate_clarification import validate_clarification_review
    from review_pipeline.stages.validate_case_intent import validate_case_intent_review

    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1

    data = read_json(args.file)
    result: ValidationResult
    basis = None

    if "decomposition" in data and "decisions" in data:
        # Looks like a clarification review
        result, basis = validate_clarification_review(str(path))
    elif "plan" in data and "decisions" in data:
        result, basis = validate_case_intent_review(str(path))
    else:
        print("Error: cannot determine review type from file content", file=sys.stderr)
        return 1

    if result.is_valid:
        print(f"Validation passed: {args.file}")
        if basis is not None:
            print(f"  Output written to {path.parent}")
        return 0
    else:
        print(f"Validation FAILED:")
        print(result.format_errors())
        return 1


def _cmd_prepare_intent_review(args: argparse.Namespace) -> int:
    from review_pipeline.stages.plan_case_intents import prepare_intent_review
    try:
        review = prepare_intent_review(args.run_dir)
        print(f"Case intent review written to {args.run_dir}/case_intent_review.json")
        if review.plan.planning_blocked:
            print(f"  PLANNING BLOCKED: {review.plan.planning_block_reason}")
        else:
            print(f"  Intents: {len(review.plan.intents)} proposed")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_generate_cases(args: argparse.Namespace) -> int:
    from review_pipeline.stages.write_cases import generate_cases
    try:
        case_set = generate_cases(args.run_dir)
        print(f"Generated cases written to {args.run_dir}/generated_cases.json")
        print(f"  Cases: {len(case_set.cases)} generated")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_evaluate(args: argparse.Namespace) -> int:
    from review_pipeline.stages.evaluate import evaluate_run
    try:
        evaluate_run(args.run_dir)
        print(f"Evaluation complete: {args.run_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_import_memory(args: argparse.Namespace) -> int:
    from review_pipeline.storage.store import import_memory
    try:
        import_memory(args.run_dir)
        print(f"Memory imported from {args.run_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m review_pipeline.cli",
        description="Clarification-first review pipeline for BMS HIL test case generation.",
    )
    sub = parser.add_subparsers(dest="command")

    p_prep = sub.add_parser("prepare-clarification-review", help="Run LLM-A: decompose requirements into clarification review")
    p_prep.add_argument("--input", required=True, help="Path to requirements JSON file")
    p_prep.add_argument("--out", required=True, help="Output run directory")
    p_prep.add_argument("--mock", action="store_true", help="Use placeholder decomposition instead of a real LLM provider")

    p_val = sub.add_parser("validate-review", help="Validate a human-edited review JSON artifact")
    p_val.add_argument("--file", required=True, help="Path to the review JSON file to validate")

    p_intent = sub.add_parser("prepare-intent-review", help="Run LLM-B: plan case intents from clarified test basis")
    p_intent.add_argument("--run-dir", required=True, help="Run directory containing clarified_test_basis.json")

    p_gen = sub.add_parser("generate-cases", help="Run LLM-C: write test cases from approved case plan")
    p_gen.add_argument("--run-dir", required=True, help="Run directory containing approved_case_plan.json")

    p_eval = sub.add_parser("evaluate", help="Run hard-rule evaluation on generated cases")
    p_eval.add_argument("--run-dir", required=True, help="Run directory containing generated_cases.json")

    p_mem = sub.add_parser("import-memory", help="Import validated review artifacts into Review Memory")
    p_mem.add_argument("--run-dir", required=True, help="Run directory containing validated review artifacts")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    handlers = {
        "prepare-clarification-review": _cmd_prepare_clarification_review,
        "validate-review": _cmd_validate_review,
        "prepare-intent-review": _cmd_prepare_intent_review,
        "generate-cases": _cmd_generate_cases,
        "evaluate": _cmd_evaluate,
        "import-memory": _cmd_import_memory,
    }

    handler = handlers.get(args.command)
    if handler:
        return handler(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
