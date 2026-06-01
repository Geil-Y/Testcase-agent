"""ABC pipeline evaluator — checklist v2 hard-rule evaluation.

Reads generated_cases.json in grouped-requirement format and runs the
optimization.evaluator engine. Writes evaluation_results.json,
evaluation_summary.json, and hardrule_evaluation.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from optimization.evaluator import evaluate_generated_cases, save_evaluation_result


def evaluate_generated_cases_file(run_dir: str | Path) -> None:
    """Evaluate generated_cases.json with checklist v2 hard-rules.

    Reads generated_cases.json, runs the shared optimization.evaluator engine,
    then writes evaluation_results.json, evaluation_summary.json, and
    hardrule_evaluation.json into the run directory.
    """
    rdir = Path(run_dir)

    cases_path = rdir / "generated_cases.json"
    if not cases_path.exists():
        raise FileNotFoundError(f"generated_cases.json not found in {run_dir}")

    data = json.loads(cases_path.read_text(encoding="utf-8"))

    # Accept both grouped-requirement list and legacy flat list.
    if _is_flat_case_list(data):
        data = _wrap_flat_as_grouped(data)

    # --- checklist v2 hard-rule evaluation ---
    result = evaluate_generated_cases(data)

    # --- per-case results ---
    eval_results = _build_evaluation_results(result)
    rdir.joinpath("evaluation_results.json").write_text(
        json.dumps(eval_results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --- aggregate summary ---
    total = result.total_cases
    passed = result.total_passed
    summary = {
        "total_cases": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round(passed / total, 4) if total > 0 else 0.0,
    }
    rdir.joinpath("evaluation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # --- hardrule_evaluation.json (prompt-debug / report tools) ---
    save_evaluation_result(result, "hardrule", rdir)


# ── helpers ──────────────────────────────────────────────────────────────


def _is_flat_case_list(data: list) -> bool:
    """Return True when data looks like a flat list of individual cases."""
    if not data:
        return False
    first = data[0]
    if not isinstance(first, dict):
        return False
    return "title" in first and "analysis" not in first


def _wrap_flat_as_grouped(flat: list[dict]) -> list[dict]:
    """Wrap a flat case list into a single-group evaluator input.

    Each case dict may carry a hidden ``_analysis`` key with the
    requirement-level analysis (signals, thresholds, timing, ...).  When
    ``_analysis`` is missing the evaluator will still run but items that
    depend on authority metadata (2.2.1, 3.2.1, 3.2.2, 3.2.3) won't fire.
    """
    if not flat:
        return []

    req_key = flat[0].get("requirement_key", "")
    analysis = flat[0].get("_analysis", {})
    description = flat[0].get("requirement_description", "")

    group = {
        "requirement_key": req_key,
        "description": description,
        "analysis": analysis,
        "cases": [_normalize_case(c, req_key) for c in flat],
    }
    return [group]


def _normalize_case(case: dict, req_key: str) -> dict:
    """Normalize ABC case dict fields to evaluator field names."""
    return {
        "title": case.get("title", ""),
        "objective": case.get("objective", ""),
        "precondition": case.get("pre_condition", case.get("precondition", "")),
        "postcondition": case.get("post_condition", case.get("postcondition", "")),
        "steps": [
            {
                "action": s.get("action", ""),
                "expected": s.get("expected_result", s.get("expected", "")),
            }
            for s in case.get("steps", [])
        ],
        "raw_html": case.get("raw_html", ""),
        "related_requirement": case.get("related_requirement", req_key),
    }


def _build_evaluation_results(result) -> list[dict]:
    results: list[dict] = []
    for (req_key, ci), ce in result.case_results.items():
        results.append({
            "case_id": f"{req_key}-case-{ci}",
            "title": ce.case_title,
            "requirement_key": req_key,
            "passed": not ce.failed_items,
            "failed_items": ce.failed_items,
            "warning_items": ce.warning_items,
        })
    return results
