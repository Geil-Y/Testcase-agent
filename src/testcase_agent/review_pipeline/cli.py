"""CLI entry point for the simplified A/B/C reviewed pipeline.

Usage: python -m testcase_agent.review_pipeline.cli <command> [options]

New artifact flow:
  LLM-A: extracted_test_basis.json -> reviewed_extracted_test_basis.json
  LLM-B: case_intents.json -> reviewed_case_intents.json
  LLM-C: generated_cases.json -> reviewed_cases.json

Legacy artifacts (clarification_review.json, clarified_test_basis.json, etc.)
are not supported by the simplified pipeline.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


# ── Run directory management ──────────────────────────────────────────────────

def _next_run_dir(out_root: str) -> Path:
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

def _cmd_extract(args: argparse.Namespace) -> int:
    """LLM-A: Extract test basis from requirement description."""
    from testcase_agent.review_pipeline.stages.extract_test_basis import extract_test_basis

    run_dir = _next_run_dir(args.out)
    try:
        run_dir.mkdir(parents=True, exist_ok=True)

        provider = None
        if not args.mock:
            from testcase_agent.config import get_settings
            from testcase_agent.provider.factory import create_provider
            provider = create_provider(get_settings())

        basis = extract_test_basis(args.input, str(run_dir), provider=provider)

        _copy_input(args.input, run_dir)

        total_items = sum(len(v) for v in basis.sections.values())
        unresolved = len(basis.all_needs_review_items())
        print(f"Run directory: {run_dir}")
        print(f"  extracted_test_basis.json — {total_items} items across 5 sections, "
              f"{unresolved} needs_review")
        if basis.has_blocking_gaps:
            print(f"  WARNING — blocking_gaps: {'; '.join(basis.blocking_gaps)}")
        return 0
    except Exception as e:
        _cleanup_empty(run_dir)
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_accept_extraction(args: argparse.Namespace) -> int:
    """Accept All: extracted_test_basis.json -> reviewed_extracted_test_basis.json."""
    from testcase_agent.review_pipeline.stages.extract_test_basis import accept_extraction
    try:
        basis = accept_extraction(args.run_dir)
        print(f"reviewed_extracted_test_basis.json — accepted")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_plan_intents(args: argparse.Namespace) -> int:
    """LLM-B: Plan case intents from reviewed extraction."""
    from testcase_agent.review_pipeline.stages.plan_case_intents import plan_intents
    try:
        provider = None
        if not args.mock:
            from testcase_agent.config import get_settings
            from testcase_agent.provider.factory import create_provider
            provider = create_provider(get_settings())
        intent_set = plan_intents(args.run_dir, provider=provider)
        print(f"case_intents.json — {len(intent_set.intents)} intents")
        if intent_set.has_blocking_gaps:
            print(f"  BLOCKED: {'; '.join(intent_set.blocking_gaps)}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_accept_intents(args: argparse.Namespace) -> int:
    """Accept All: case_intents.json -> reviewed_case_intents.json."""
    from testcase_agent.review_pipeline.stages.plan_case_intents import accept_intents
    try:
        intent_set = accept_intents(args.run_dir)
        print(f"reviewed_case_intents.json — {len(intent_set.intents)} intents accepted")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_generate_cases(args: argparse.Namespace) -> int:
    """LLM-C: Generate test cases from reviewed artifacts."""
    from testcase_agent.review_pipeline.stages.write_cases import generate_cases
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


def _cmd_accept_cases(args: argparse.Namespace) -> int:
    """Accept All: generated_cases.json -> reviewed_cases.json."""
    from testcase_agent.review_pipeline.stages.write_cases import accept_cases
    try:
        case_set = accept_cases(args.run_dir)
        print(f"reviewed_cases.json — {len(case_set.cases)} cases accepted")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_regenerate(args: argparse.Namespace) -> int:
    """Regenerate a case with a review comment."""
    import json
    from testcase_agent.review_pipeline.stages.write_cases import regenerate_and_save
    from testcase_agent.review_pipeline.artifacts.models import RegenerateRequest
    try:
        provider = None
        if not args.mock:
            from testcase_agent.config import get_settings
            from testcase_agent.provider.factory import create_provider
            provider = create_provider(get_settings())

        requests_data = json.loads(Path(args.requests).read_text(encoding="utf-8"))
        requests = [RegenerateRequest(**r) for r in requests_data]

        case_set = regenerate_and_save(args.run_dir, requests, provider=provider)
        print(f"reviewed_cases.json — {len(case_set.cases)} cases after regenerate")
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
        files = [f.name for f in r.iterdir() if f.is_file()]
        reviewing = "reviewed_" in str(files)
        marker = " [reviewed]" if reviewing else ""
        print(f"  {r.name}{marker}")
    return 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cleanup_empty(run_dir: Path) -> None:
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


# ── Legacy handlers (for backward compatibility) ──────────────────────────

def _cmd_validate_review_legacy(args: argparse.Namespace) -> int:
    """[DEPRECATED] Legacy validation command."""
    from testcase_agent.review_pipeline.stages.validate_clarification import validate_clarification_review
    from testcase_agent.review_pipeline.stages.validate_case_intent import validate_case_intent_review
    from testcase_agent.review_pipeline.artifacts.io import read_json

    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1

    data = read_json(args.file)
    result = None
    basis = None

    if "decomposition" in data and "decisions" in data:
        result, basis = validate_clarification_review(str(path))
    elif "plan" in data and "decisions" in data:
        result, basis = validate_case_intent_review(str(path))
    else:
        print("Error: cannot determine review type from file content", file=sys.stderr)
        return 1

    if result and result.is_valid:
        print(f"Validation passed: {args.file}")
        return 0
    elif result:
        print("Validation FAILED:")
        print(result.format_errors())
        return 1
    return 0


def _cmd_evaluate_legacy(args: argparse.Namespace) -> int:
    """[DEPRECATED] Legacy evaluation command."""
    from testcase_agent.review_pipeline.stages.evaluate import evaluate_run
    try:
        evaluate_run(args.run_dir)
        print("Evaluation complete")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_generate_report_legacy(args: argparse.Namespace) -> int:
    """[DEPRECATED] Legacy report command."""
    try:
        from testcase_agent.review_pipeline.html_rendering.report import render_unified_report
        rdir = Path(args.run_dir)
        html = render_unified_report(rdir)
        (rdir / "review_report.html").write_text(html, encoding="utf-8")
        print("review_report.html generated")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _cmd_import_memory_legacy(args: argparse.Namespace) -> int:
    """[DEPRECATED] Legacy memory import command."""
    try:
        from testcase_agent.review_pipeline.storage.store import import_memory
        import_memory(args.run_dir)
        print(f"Memory imported from {args.run_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


# ── Parser ────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m testcase_agent.review_pipeline.cli",
        description="Simplified A/B/C reviewed pipeline for BMS HIL test case generation.",
    )
    sub = parser.add_subparsers(dest="command")

    # LLM-A: Extraction
    p_extract = sub.add_parser("extract", help="LLM-A: extract test basis from requirement description")
    p_extract.add_argument("--input", required=True, help="Path to requirements JSON file")
    p_extract.add_argument("--out", required=True, help="Output root directory")
    p_extract.add_argument("--mock", action="store_true", help="Use placeholder instead of real LLM")

    p_accept_a = sub.add_parser("accept-extraction", help="Accept All: write reviewed_extracted_test_basis.json")
    p_accept_a.add_argument("--run-dir", required=True, help="Run directory containing extracted_test_basis.json")

    # LLM-B: Intent planning
    p_plan = sub.add_parser("plan-intents", help="LLM-B: plan case intents from reviewed extraction")
    p_plan.add_argument("--run-dir", required=True, help="Run directory containing reviewed_extracted_test_basis.json")
    p_plan.add_argument("--mock", action="store_true", help="Use placeholder instead of real LLM")

    p_accept_b = sub.add_parser("accept-intents", help="Accept All: write reviewed_case_intents.json")
    p_accept_b.add_argument("--run-dir", required=True, help="Run directory containing case_intents.json")

    # LLM-C: Case generation
    p_gen = sub.add_parser("generate-cases", help="LLM-C: write test cases from reviewed artifacts")
    p_gen.add_argument("--run-dir", required=True, help="Run directory containing reviewed artifacts")
    p_gen.add_argument("--mock", action="store_true", help="Use placeholder instead of real LLM")

    p_accept_c = sub.add_parser("accept-cases", help="Accept All: write reviewed_cases.json")
    p_accept_c.add_argument("--run-dir", required=True, help="Run directory containing generated_cases.json")

    p_regen = sub.add_parser("regenerate", help="Regenerate case(s) with review comment(s)")
    p_regen.add_argument("--run-dir", required=True, help="Run directory containing reviewed artifacts")
    p_regen.add_argument("--requests", required=True, help="JSON file with list of RegenerateRequest objects")
    p_regen.add_argument("--mock", action="store_true", help="Use placeholder instead of real LLM")

    p_list = sub.add_parser("list-runs", help="List all runs in the output directory")
    p_list.add_argument("--out", default="reviews", help="Output root directory (default: reviews/)")

    # Legacy commands — registered so argparse recognizes them, but all route to unsupported.
    # Add common legacy arguments so --file, --input, --out, --run-dir are accepted silently.
    def _add_legacy(name, help_text):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--file", default="", help=argparse.SUPPRESS)
        p.add_argument("--input", default="", help=argparse.SUPPRESS)
        p.add_argument("--out", default="", help=argparse.SUPPRESS)
        p.add_argument("--run-dir", default="", help=argparse.SUPPRESS)
        p.add_argument("--mock", action="store_true", help=argparse.SUPPRESS)
        return p

    _add_legacy("prepare-clarification-review",
                "[UNSUPPORTED] Legacy command from facts/ambiguities pipeline")
    _add_legacy("validate-review",
                "[UNSUPPORTED] Legacy validation command")
    _add_legacy("prepare-intent-review",
                "[UNSUPPORTED] Legacy intent planning command")
    _add_legacy("evaluate",
                "[UNSUPPORTED] Legacy evaluation command")
    _add_legacy("generate-report",
                "[UNSUPPORTED] Legacy report command")
    _add_legacy("import-memory",
                "[UNSUPPORTED] Legacy memory import command")

    return parser


_LEGACY_COMMANDS = frozenset({
    "prepare-clarification-review", "validate-review", "prepare-intent-review",
    "evaluate", "generate-report", "import-memory",
})


def _legacy_unsupported(args: argparse.Namespace) -> int:
    """Print unsupported message for legacy commands."""
    print("ERROR: This command is from the legacy facts/ambiguities pipeline "
          "which is no longer supported.", file=sys.stderr)
    print("Use the simplified pipeline: extract -> accept-extraction -> plan-intents -> "
          "accept-intents -> generate-cases -> accept-cases", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command in _LEGACY_COMMANDS:
        return _legacy_unsupported(args)

    handlers = {
        "extract": _cmd_extract,
        "accept-extraction": _cmd_accept_extraction,
        "plan-intents": _cmd_plan_intents,
        "accept-intents": _cmd_accept_intents,
        "generate-cases": _cmd_generate_cases,
        "accept-cases": _cmd_accept_cases,
        "regenerate": _cmd_regenerate,
        "list-runs": _cmd_list_runs,
    }

    handler = handlers.get(args.command)
    if handler:
        return handler(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
