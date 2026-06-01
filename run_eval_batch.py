#!/usr/bin/env python3
"""Batch evaluation: process requirements through ABC pipeline.

Usage:
  python run_eval_batch.py --pipeline minimal  [--limit N] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(description="Batch eval with selectable pipeline")
    parser.add_argument(
        "--pipeline",
        choices=["minimal"],
        default="minimal",
        help="Pipeline mode (default: minimal)",
    )
    parser.add_argument(
        "--requirement-set",
        default="optimization_runs/requirement_sets/prompt_eval_v1.json",
        help="Path to requirement set JSON",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process first N requirements only")
    parser.add_argument("--out", default="reviews", help="Output root directory")
    args = parser.parse_args()

    # 1. Load requirement set
    set_path = _PROJECT_ROOT / args.requirement_set
    if not set_path.exists():
        print(f"ERROR: requirement set not found: {set_path}")
        return 1

    with open(set_path, encoding="utf-8") as f:
        req_set = json.load(f)

    entries = req_set["entries"]
    if args.limit:
        entries = entries[: args.limit]

    print(f"Pipeline: {args.pipeline}")
    print(f"Requirement set: {req_set['name']}")
    print(f"Entries: {len(entries)} (limit={args.limit})")

    # 2. Create provider
    from testcase_agent.config import get_settings
    from testcase_agent.provider.factory import create_provider

    settings = get_settings()
    provider = create_provider(settings)
    print(f"Provider: {type(provider).__name__}")

    # 3. Create batch output directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    batch_root = _PROJECT_ROOT / args.out / f"batch_eval_{args.pipeline}_{ts}"
    batch_root.mkdir(parents=True, exist_ok=True)
    print(f"Output: {batch_root}")

    _run_minimal_batch(entries, batch_root, provider, req_set)


def _run_minimal_batch(entries: list[dict], batch_root: Path, provider, req_set: dict) -> None:
    from testcase_agent.pipeline.generate import RequirementInput, run_pipeline
    from src.testcase_agent.pipeline.evaluate import evaluate_generated_cases_file

    batch_results: list[dict] = []
    total_cases = 0
    total_passed = 0
    total_failed = 0
    errors_count = 0
    completed_count = 0

    for idx, entry in enumerate(entries):
        req_key = entry["requirement_key"]
        print(f"\n{'='*60}")
        print(f"[{idx+1}/{len(entries)}] {req_key} — {entry.get('function_name', '')}")
        print(f"{'='*60}")

        req_dir = batch_root / req_key
        result_entry: dict = {
            "requirement_key": req_key,
            "function_name": entry.get("function_name", ""),
            "evaluation_bucket": entry.get("evaluation_bucket", ""),
            "num_cases": 0,
            "passed": 0,
            "failed": 0,
            "pass_rate": 0.0,
            "run_dir": str(req_dir),
            "error": None,
        }

        try:
            req_dir.mkdir(parents=True, exist_ok=True)

            req_input = RequirementInput(
                requirement_key=req_key,
                description=entry["description"],
                function_name=entry.get("function_name", ""),
                supplementary_info="",
            )

            # Run ABC pipeline
            print(f"  [ABC] run_pipeline ...")
            result = run_pipeline(req_input, provider)

            if result.error:
                raise RuntimeError(result.error)

            assert result.intent_plan is not None
            assert result.test_basis is not None
            num_cases = len(result.cases)
            print(f"  [ABC] {num_cases} cases generated")

            # Write grouped evaluator input (with analysis metadata)
            grouped = _build_grouped_evaluator_input(
                result, req_key, entry.get("description", "")
            )
            req_dir.joinpath("generated_cases.json").write_text(
                json.dumps(grouped, ensure_ascii=False, indent=2), encoding="utf-8",
            )

            # Evaluate with checklist v2 hard-rules
            print(f"  [Evaluate] checklist v2 hard-rule checks ...")
            evaluate_generated_cases_file(str(req_dir))

            # Collect results
            eval_summary_path = req_dir / "evaluation_summary.json"
            if eval_summary_path.exists():
                eval_summary = json.loads(eval_summary_path.read_text(encoding="utf-8"))
                result_entry["num_cases"] = eval_summary["total_cases"]
                result_entry["passed"] = eval_summary["passed"]
                result_entry["failed"] = eval_summary["failed"]
                result_entry["pass_rate"] = eval_summary["pass_rate"]

                total_cases += result_entry["num_cases"]
                total_passed += result_entry["passed"]
                total_failed += result_entry["failed"]
                completed_count += 1

                print(f"  Done: {result_entry['num_cases']} cases, {result_entry['passed']} passed, {result_entry['failed']} failed")
            else:
                print(f"  Done: {num_cases} cases (no evaluation summary)")

        except Exception as exc:
            result_entry["error"] = f"{type(exc).__name__}: {exc}"
            errors_count += 1
            print(f"  ERROR: {exc}")
            traceback.print_exc()

        batch_results.append(result_entry)

    _write_batch_summary(batch_root, req_set, entries, batch_results,
                         completed_count, errors_count, total_cases,
                         total_passed, total_failed, "minimal")


def _build_grouped_evaluator_input(
    result, req_key: str, description: str
) -> list[dict]:
    """Build grouped evaluator input with analysis metadata from pipeline result.

    Produces the format expected by optimization.evaluator.evaluate_generated_cases().
    """
    from testcase_agent.pipeline.generate import GenerationResult

    test_basis = result.test_basis
    intent_plan = result.intent_plan

    # Build cases list from GeneratedCase objects
    cases: list[dict] = []
    for i, case in enumerate(result.cases):
        intent = intent_plan.case_intents[i] if i < len(intent_plan.case_intents) else None
        steps = []
        for step in case.steps:
            steps.append({
                "action": step.action,
                "expected": step.expected or "",
            })
        cases.append({
            "title": case.title,
            "objective": case.objective,
            "precondition": case.precondition,
            "postcondition": case.postcondition,
            "steps": steps,
            "raw_html": case.raw_html,
            "related_requirement": req_key,
            "coverage_dimension": intent.coverage_dimension if intent else "",
        })

    # Build analysis from test_basis
    missing_info_items = [
        {"category": mi.category, "description": mi.description}
        for mi in test_basis.missing_info
    ]
    case_intents = [
        {"coverage": intent.coverage_dimension}
        for intent in intent_plan.case_intents
    ]

    analysis = {
        "signals": list(test_basis.allowed_signals),
        "thresholds": list(test_basis.allowed_thresholds),
        "timing": list(test_basis.allowed_timing),
        "missing_info_items": missing_info_items,
        "case_intents": case_intents,
    }

    return [{
        "requirement_key": req_key,
        "description": description,
        "analysis": analysis,
        "cases": cases,
    }]


def _write_batch_summary(
    batch_root: Path,
    req_set: dict,
    entries: list[dict],
    batch_results: list[dict],
    completed_count: int,
    errors_count: int,
    total_cases: int,
    total_passed: int,
    total_failed: int,
    pipeline_mode: str,
) -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    aggregate_pass_rate = total_passed / total_cases if total_cases > 0 else 0.0
    batch_summary = {
        "run_name": f"batch_eval_{pipeline_mode}_{ts}",
        "timestamp": datetime.now().isoformat(),
        "requirement_set": req_set["name"],
        "pipeline_mode": pipeline_mode,
        "total_requirements": len(entries),
        "completed": completed_count,
        "failed": errors_count,
        "total_cases": total_cases,
        "total_passed": total_passed,
        "total_failed": total_failed,
        "aggregate_pass_rate": round(aggregate_pass_rate, 4),
        "results": batch_results,
    }
    summary_path = batch_root / "batch_results.json"
    summary_path.write_text(
        json.dumps(batch_summary, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(f"\nBatch results: {summary_path}")

    batch_html = _render_batch_html(batch_summary, pipeline_mode)
    report_path = batch_root / "batch_report.html"
    report_path.write_text(batch_html, encoding="utf-8")
    print(f"Batch report: {report_path}")

    print(f"\n{'='*60}")
    print(f"DONE. {completed_count}/{len(entries)} requirements completed, {errors_count} errors")
    print(f"Total cases: {total_cases}, Passed: {total_passed}, Failed: {total_failed}")
    print(f"Aggregate pass rate: {aggregate_pass_rate:.1%}")
    print(f"Output: {batch_root}")


def _render_batch_html(summary: dict, pipeline_mode: str) -> str:
    results = summary["results"]
    total = summary["total_requirements"]
    completed = summary["completed"]
    failed = summary["failed"]
    total_cases = summary["total_cases"]
    pass_rate = summary["aggregate_pass_rate"]

    def rate_color(rate: float) -> str:
        if rate >= 0.9:
            return "#22c55e"
        if rate >= 0.7:
            return "#eab308"
        return "#ef4444"

    rows_html = ""
    for r in results:
        rk = r["requirement_key"]
        fn = r.get("function_name", "")
        bucket = r.get("evaluation_bucket", "")
        nc = r["num_cases"]
        ps = r["passed"]
        fl = r["failed"]
        pr = r["pass_rate"]
        err = r.get("error")
        run_dir = r.get("run_dir", "")

        if err:
            status_cell = f'<td style="color:#ef4444;font-weight:600">ERROR</td>'
            rate_cell = '<td>-</td>'
            detail_link = f'<td style="color:#ef4444;font-size:12px">{err}</td>'
        else:
            color = rate_color(pr)
            status_cell = f'<td style="color:{color};font-weight:600">{pr:.0%}</td>'
            rate_cell = f'<td style="color:{color}">{pr:.0%}</td>'
            if pipeline_mode == "minimal":
                report_path = f"{Path(run_dir).name}/generated_cases.json"
            else:
                report_path = f"{Path(run_dir).name}/review_report.html"
            detail_link = f'<td><a href="{report_path}" target="_blank">View cases</a></td>'

        rows_html += f"""
        <tr>
            <td>{rk}</td>
            <td>{fn}</td>
            <td style="font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="{bucket}">{bucket}</td>
            <td style="text-align:center">{nc}</td>
            <td style="text-align:center">{ps}</td>
            <td style="text-align:center">{fl}</td>
            {rate_cell}
            {status_cell}
            {detail_link}
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Batch Eval Report ({pipeline_mode}) - {summary['run_name']}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 40px; background: #f8fafc; color: #1e293b; }}
  h1 {{ margin-bottom: 4px; }}
  .meta {{ color: #64748b; font-size: 14px; margin-bottom: 24px; }}
  .cards {{ display: flex; gap: 16px; margin-bottom: 32px; flex-wrap: wrap; }}
  .card {{ background: #fff; border-radius: 10px; padding: 20px 28px; box-shadow: 0 1px 3px rgba(0,0,0,.08); min-width: 140px; }}
  .card .value {{ font-size: 28px; font-weight: 700; }}
  .card .label {{ font-size: 13px; color: #64748b; margin-top: 2px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  th {{ background: #f1f5f9; padding: 10px 12px; text-align: left; font-size: 13px; font-weight: 600; color: #475569; }}
  td {{ padding: 10px 12px; border-top: 1px solid #e2e8f0; font-size: 14px; }}
  tr:hover {{ background: #f8fafc; }}
  a {{ color: #3b82f6; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
<h1>Batch Evaluation Report ({pipeline_mode})</h1>
<p class="meta">
  Dataset: {summary['requirement_set']} &middot;
  Run: {summary['run_name']} &middot;
  Timestamp: {summary['timestamp']}
</p>

<div class="cards">
  <div class="card"><div class="value">{total}</div><div class="label">Requirements</div></div>
  <div class="card"><div class="value" style="color:#22c55e">{completed}</div><div class="label">Completed</div></div>
  <div class="card"><div class="value" style="color:#ef4444">{failed}</div><div class="label">Errors</div></div>
  <div class="card"><div class="value">{total_cases}</div><div class="label">Total Cases</div></div>
  <div class="card"><div class="value" style="color:{rate_color(pass_rate)}">{pass_rate:.0%}</div><div class="label">Aggregate Pass Rate</div></div>
</div>

<table>
<thead>
<tr>
  <th>Requirement Key</th>
  <th>Function</th>
  <th>Bucket</th>
  <th style="text-align:center">Cases</th>
  <th style="text-align:center">Passed</th>
  <th style="text-align:center">Failed</th>
  <th style="text-align:center">Pass Rate</th>
  <th style="text-align:center">Status</th>
  <th>Detail</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</body>
</html>"""


if __name__ == "__main__":
    sys.exit(main())
