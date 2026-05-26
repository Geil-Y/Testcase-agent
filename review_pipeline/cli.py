"""CLI entry point for the review pipeline.

Usage: python -m review_pipeline.cli <command> [options]

Output convention:
  All review artifacts live under a root output directory (default: reviews/).
  Each pipeline run creates an auto-numbered subdirectory:
    reviews/run_001/   reviews/run_002/   ...
  Within each run directory, artifacts are named by pipeline stage:
    00_requirements.json       (input copy)
    01_clarification_review.json
    01_clarification_review.html
    02_clarified_test_basis.json
    03_case_intent_review.json
    03_case_intent_review.html
    04_approved_case_plan.json
    05_generated_cases.json
    06_evaluation.json
    review_report.html         (unified human-review report)
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from review_pipeline.artifacts.io import read_json, write_json
from review_pipeline.artifacts.validation import ValidationResult


# ── Run directory management ──────────────────────────────────────────────────

def _next_run_dir(out_root: str) -> Path:
    """Find the next available run_NNN directory under out_root."""
    root = Path(out_root)
    root.mkdir(parents=True, exist_ok=True)
    existing = sorted([d for d in root.iterdir() if d.is_dir() and d.name.startswith("run_")])
    if not existing:
        return root / "run_001"
    last_num = 0
    for d in existing:
        try:
            num = int(d.name.split("_")[1])
            last_num = max(last_num, num)
        except (IndexError, ValueError):
            continue
    return root / f"run_{last_num + 1:03d}"


# ── Stage handlers ────────────────────────────────────────────────────────────

def _cmd_prepare_clarification_review(args: argparse.Namespace) -> int:
    from review_pipeline.stages.decompose_requirement import prepare_clarification_review
    run_dir = _next_run_dir(args.out)
    try:
        run_dir.mkdir(parents=True, exist_ok=True)

        provider = None
        if not args.mock:
            from testcase_agent.config import get_settings
            from testcase_agent.provider.factory import create_provider
            provider = create_provider(get_settings())

        review = prepare_clarification_review(args.input, str(run_dir), provider=provider)

        _copy_input(args.input, run_dir)

        print(f"Run directory: {run_dir}")
        print(f"  clarification_review.json — {len(review.decomposition.facts)} facts, {len(review.decomposition.ambiguities)} ambiguities")
        return 0
    except Exception as e:
        _cleanup_empty(run_dir)
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
        provider = None
        if not args.mock:
            from testcase_agent.config import get_settings
            from testcase_agent.provider.factory import create_provider
            provider = create_provider(get_settings())
        review = prepare_intent_review(args.run_dir, provider=provider)
        print(f"case_intent_review.json — {len(review.plan.intents)} intents")
        if review.plan.planning_blocked:
            print(f"  PLANNING BLOCKED: {review.plan.planning_block_reason}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_generate_cases(args: argparse.Namespace) -> int:
    from review_pipeline.stages.write_cases import generate_cases
    try:
        provider = None
        if not args.mock:
            from testcase_agent.config import get_settings
            from testcase_agent.provider.factory import create_provider
            provider = create_provider(get_settings())
        case_set = generate_cases(args.run_dir, provider=provider)
        print(f"generated_cases.json — {len(case_set.cases)} cases")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_evaluate(args: argparse.Namespace) -> int:
    from review_pipeline.stages.evaluate import evaluate_run
    from review_pipeline.html_rendering.report import render_unified_report
    try:
        evaluate_run(args.run_dir)
        print(f"06_evaluation.json — complete")
        _generate_report(Path(args.run_dir))
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_generate_report(args: argparse.Namespace) -> int:
    from review_pipeline.html_rendering.report import render_unified_report
    try:
        _generate_report(Path(args.run_dir))
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


def _cmd_list_runs(args: argparse.Namespace) -> int:
    root = Path(args.out)
    if not root.exists():
        print(f"No runs found in {root}")
        return 0
    runs = sorted([d for d in root.iterdir() if d.is_dir() and d.name.startswith("run_")])
    if not runs:
        print(f"No runs found in {root}")
        return 0
    print(f"Runs in {root}:")
    for r in runs:
        has_report = (r / "review_report.html").exists()
        marker = " [report]" if has_report else ""
        print(f"  {r.name}{marker}")
    return 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cleanup_empty(run_dir: Path) -> None:
    """Remove run directory if empty (created but pipeline failed)."""
    try:
        if run_dir.exists():
            contents = list(run_dir.iterdir())
            if not contents:
                run_dir.rmdir()
    except OSError:
        pass


def _copy_input(input_path: str, run_dir: Path) -> None:
    src = Path(input_path)
    if not src.exists():
        return
    dst = run_dir / "00_requirements.json"
    if not dst.exists():
        shutil.copy2(src, dst)


def _generate_report(run_dir: Path) -> None:
    from review_pipeline.html_rendering.report import render_unified_report
    html = render_unified_report(run_dir)
    report_path = run_dir / "review_report.html"
    report_path.write_text(html, encoding="utf-8")
    print(f"  review_report.html — unified report")


# ── Parser ────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m review_pipeline.cli",
        description="Clarification-first review pipeline for BMS HIL test case generation.",
    )
    sub = parser.add_subparsers(dest="command")

    p_prep = sub.add_parser("prepare-clarification-review", help="LLM-A: decompose requirements into clarification review")
    p_prep.add_argument("--input", required=True, help="Path to requirements JSON file")
    p_prep.add_argument("--out", required=True, help="Output root directory (auto-creates run_NNN inside)")
    p_prep.add_argument("--mock", action="store_true", help="Use placeholder decomposition instead of real LLM")

    p_val = sub.add_parser("validate-review", help="Validate a human-edited review JSON artifact")
    p_val.add_argument("--file", required=True, help="Path to the review JSON file to validate")

    p_intent = sub.add_parser("prepare-intent-review", help="LLM-B: plan case intents from clarified test basis")
    p_intent.add_argument("--run-dir", required=True, help="Run directory containing clarified_test_basis.json")
    p_intent.add_argument("--mock", action="store_true", help="Use placeholder intents instead of real LLM")

    p_gen = sub.add_parser("generate-cases", help="LLM-C: write test cases from approved case plan")
    p_gen.add_argument("--run-dir", required=True, help="Run directory containing approved_case_plan.json")
    p_gen.add_argument("--mock", action="store_true", help="Use placeholder cases instead of real LLM")

    p_eval = sub.add_parser("evaluate", help="Run hard-rule evaluation on generated cases")
    p_eval.add_argument("--run-dir", required=True, help="Run directory containing generated_cases.json")

    p_report = sub.add_parser("generate-report", help="Generate unified review_report.html for a run")
    p_report.add_argument("--run-dir", required=True, help="Run directory with pipeline artifacts")

    p_mem = sub.add_parser("import-memory", help="Import validated review artifacts into Review Memory")
    p_mem.add_argument("--run-dir", required=True, help="Run directory containing validated review artifacts")

    p_list = sub.add_parser("list-runs", help="List all runs in the output directory")
    p_list.add_argument("--out", default="reviews", help="Output root directory (default: reviews/)")

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
        "generate-report": _cmd_generate_report,
        "import-memory": _cmd_import_memory,
        "list-runs": _cmd_list_runs,
    }

    handler = handlers.get(args.command)
    if handler:
        return handler(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
