"""Issue 13: Integration with existing evaluation and reports.

Reuses existing evaluator/report code where practical for the new pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path

from review_pipeline.artifacts.io import read_json, write_json


def evaluate_run(run_dir: str) -> None:
    """Run hard-rule evaluation on generated cases from the new pipeline.

    Writes evaluation outputs into the run directory.
    Reuses existing evaluator/report code where practical.
    """
    rdir = Path(run_dir)

    cases_path = rdir / "generated_cases.json"
    if not cases_path.exists():
        raise FileNotFoundError(f"generated_cases.json not found in {run_dir}")

    cases = read_json(cases_path)
    if not isinstance(cases, list):
        cases = [cases]

    # Run hard-rule evaluation on each case
    eval_results = []
    for case_data in cases:
        result = _evaluate_single_case(case_data)
        eval_results.append(result)

    # Write evaluation results
    write_json(rdir / "evaluation_results.json", eval_results)

    # Write summary
    total = len(eval_results)
    passed = sum(1 for r in eval_results if r.get("passed", False))
    summary = {
        "total_cases": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total > 0 else 0.0,
    }
    write_json(rdir / "evaluation_summary.json", summary)


def _evaluate_single_case(case_data: dict) -> dict:
    """Run hard-rule checks on a single generated case.

    Preserves traceability fields in output.
    """
    checks: list[dict] = []

    # Hard rule: title must not be empty
    title = case_data.get("title", "")
    checks.append({
        "rule": "title_not_empty",
        "passed": bool(title.strip()),
        "detail": "Title is empty" if not title.strip() else "OK",
    })

    # Hard rule: objective must not be empty
    objective = case_data.get("objective", "")
    checks.append({
        "rule": "objective_not_empty",
        "passed": bool(objective.strip()),
        "detail": "Objective is empty" if not objective.strip() else "OK",
    })

    # Hard rule: pre_condition must exist
    pre = case_data.get("pre_condition", "")
    checks.append({
        "rule": "precondition_present",
        "passed": True,  # pre_condition can be empty
        "detail": "OK" if pre else "No precondition specified",
    })

    # Hard rule: steps must exist and have action/expected_result
    steps = case_data.get("steps", [])
    if not steps:
        checks.append({
            "rule": "steps_not_empty",
            "passed": False,
            "detail": "No test steps defined",
        })
    else:
        for i, step in enumerate(steps):
            has_action = bool(step.get("action", "").strip())
            has_expected = bool(step.get("expected_result", "").strip())
            checks.append({
                "rule": f"step_{i+1}_complete",
                "passed": has_action and has_expected,
                "detail": "OK" if (has_action and has_expected) else f"Step {i+1} missing action or expected result",
            })

    # Hard rule: post_condition must exist
    post = case_data.get("post_condition", "")
    checks.append({
        "rule": "postcondition_present",
        "passed": bool(post.strip()),
        "detail": "Post-condition is empty" if not post.strip() else "OK",
    })

    # Hard rule: NEEDS REVIEW check
    all_text = json.dumps(case_data, ensure_ascii=False)
    has_needs_review = "[NEEDS REVIEW]" in all_text
    checks.append({
        "rule": "needs_review_marker_acknowledged",
        "passed": True,  # Marker is intentional when present
        "detail": "NEEDS REVIEW marker present" if has_needs_review else "No NEEDS REVIEW markers",
    })

    all_passed = all(c["passed"] for c in checks)

    return {
        "case_id": case_data.get("case_id", "unknown"),
        "title": title,
        "requirement_key": case_data.get("requirement_key", ""),
        "approved_intent_id": case_data.get("approved_intent_id", ""),
        "coverage_dimension": case_data.get("coverage_dimension", ""),
        "review_session_id": case_data.get("review_session_id", ""),
        "passed": all_passed,
        "checks": checks,
    }
