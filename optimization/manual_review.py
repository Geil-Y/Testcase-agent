"""Manual Review Score — human-scored 8-dimension rubric.

Manual review follows the same scoring model as the DeepSeek evaluator:

- coverage_value is scored once per requirement over the full generated case set.
- the other seven dimensions are scored per case.
- weighted scores are computed per requirement, then averaged across
  requirements so requirements with more generated cases do not dominate the
  run-level score.

Hard gates remain separate from weighted scoring and reuse the shared evaluator
logic for deterministic [NEEDS REVIEW] checks.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_VALID_SCORES = {1, 2, 3, 4, 5}
CASE_LEVEL_DIMS = [
    "requirement_alignment",
    "executability",
    "observability",
    "pass_fail_clarity",
    "information_integrity",
    "state_and_environment_control",
    "automation_readiness",
]
ALL_DIMS = [
    "requirement_alignment",
    "coverage_value",
    "executability",
    "observability",
    "pass_fail_clarity",
    "information_integrity",
    "state_and_environment_control",
    "automation_readiness",
]
_WEIGHTS = {
    "requirement_alignment": 0.20,
    "information_integrity": 0.20,
    "executability": 0.15,
    "observability": 0.15,
    "pass_fail_clarity": 0.10,
    "coverage_value": 0.10,
    "state_and_environment_control": 0.05,
    "automation_readiness": 0.05,
}


@dataclass
class ReviewCaseEntry:
    requirement_key: str
    case_index: int
    requirement_alignment: int
    executability: int
    observability: int
    pass_fail_clarity: int
    information_integrity: int
    state_and_environment_control: int
    automation_readiness: int
    reviewer: str = ""
    notes: str = ""


@dataclass
class ReviewRequirementEntry:
    requirement_key: str
    coverage_value: int
    cases: list[ReviewCaseEntry] = field(default_factory=list)
    reviewer: str = ""
    notes: str = ""
    coverage_value_note: str = ""


@dataclass
class HardGateResult:
    unacceptable: bool = False
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _validate_score(item: dict, field: str, context: str) -> int:
    val = item.get(field)
    if val not in _VALID_SCORES:
        raise ValueError(f"{context}: '{field}' must be 1-5, got {val!r}")
    return int(val)


def load_review_scores(path: str | Path) -> list[ReviewRequirementEntry]:
    """Load and validate a manual_review_scores.json file.

    The preferred schema is a JSON object with a `requirements` array, or a
    direct array of requirement entries:

    {
      "requirements": [
        {
          "requirement_key": "R1",
          "coverage_value": 4,
          "cases": [
            {
              "case_index": 0,
              "requirement_alignment": 5,
              "executability": 4,
              "observability": 4,
              "pass_fail_clarity": 3,
              "information_integrity": 5,
              "state_and_environment_control": 4,
              "automation_readiness": 4
            }
          ]
        }
      ]
    }

    Raises ValueError on schema or score-range errors.
    """
    path = Path(path)
    if not path.exists():
        raise ValueError(f"Review file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Review file is not valid JSON: {exc}") from exc

    if isinstance(data, dict):
        req_items = data.get("requirements")
    else:
        req_items = data

    if not isinstance(req_items, list):
        raise ValueError("Review file must contain a 'requirements' array or a JSON array")

    entries: list[ReviewRequirementEntry] = []
    for i, item in enumerate(req_items):
        if not isinstance(item, dict):
            raise ValueError(f"Requirement entry {i} is not a JSON object")
        if "cases" not in item:
            raise ValueError(
                f"Requirement entry {i}: expected 8-dimension requirement-level "
                "schema with 'coverage_value' and 'cases'"
            )

        key = item.get("requirement_key")
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"Requirement entry {i}: missing or empty 'requirement_key'")
        context = f"Requirement entry {i} ('{key}')"
        coverage_value = _validate_score(item, "coverage_value", context)

        cases_raw = item.get("cases")
        if not isinstance(cases_raw, list) or not cases_raw:
            raise ValueError(f"{context}: 'cases' must be a non-empty array")

        cases: list[ReviewCaseEntry] = []
        for j, case_item in enumerate(cases_raw):
            if not isinstance(case_item, dict):
                raise ValueError(f"{context}: case entry {j} is not a JSON object")
            ci = case_item.get("case_index")
            if not isinstance(ci, int) or ci < 0:
                raise ValueError(f"{context}: case entry {j} 'case_index' must be a non-negative integer")
            case_context = f"{context} case_index={ci}"
            scores = {
                dim: _validate_score(case_item, dim, case_context)
                for dim in CASE_LEVEL_DIMS
            }
            cases.append(ReviewCaseEntry(
                requirement_key=key.strip(),
                case_index=ci,
                reviewer=case_item.get("reviewer", item.get("reviewer", "")),
                notes=case_item.get("notes", ""),
                **scores,
            ))

        entries.append(ReviewRequirementEntry(
            requirement_key=key.strip(),
            coverage_value=coverage_value,
            coverage_value_note=item.get("coverage_value_note", ""),
            reviewer=item.get("reviewer", ""),
            notes=item.get("notes", ""),
            cases=cases,
        ))

    return entries


def _avg_case_dim(entry: ReviewRequirementEntry, dim: str) -> float:
    vals = [getattr(c, dim) for c in entry.cases]
    return sum(vals) / len(vals) if vals else 0.0


def _min_case_dim(entry: ReviewRequirementEntry, dim: str) -> int:
    vals = [getattr(c, dim) for c in entry.cases]
    return min(vals) if vals else 0


def compute_weighted_score(entry: ReviewRequirementEntry) -> float:
    """Compute the 0-5 per-requirement weighted score.

    coverage_value is requirement-level. The other seven dimensions are first
    averaged across cases under the same requirement.
    """
    w = _WEIGHTS["coverage_value"] * entry.coverage_value
    for dim in CASE_LEVEL_DIMS:
        w += _WEIGHTS[dim] * _avg_case_dim(entry, dim)
    return round(w, 1)


def apply_hard_gates(
    entry: ReviewCaseEntry,
    generated_case: dict | None = None,
    expected_missing_categories: list[str] | None = None,
) -> HardGateResult:
    """Apply hard gates before accepting any weighted score."""
    from optimization.evaluator import evaluate_manual_review_hard_gates

    gate = evaluate_manual_review_hard_gates(
        entry,
        generated_case,
        expected_missing_categories,
    )
    return HardGateResult(
        unacceptable=gate["unacceptable"],
        reasons=gate["reasons"],
        warnings=gate["warnings"],
    )


# -- Summary helpers for report rendering --------------------------------

def get_review_summary(
    entries: list[ReviewRequirementEntry],
    generated_data: list[dict],
) -> dict:
    """Compute aggregate manual review stats for the report."""
    if not entries:
        return {}

    case_lookup: dict[tuple[str, int], dict] = {}
    req_meta: dict[str, list[str]] = {}
    req_case_counts: dict[str, int] = {}
    for req in generated_data:
        key = req["requirement_key"]
        req_meta[key] = req.get("expected_missing_categories", [])
        cases = req.get("cases", [])
        req_case_counts[key] = len(cases)
        for ci, case in enumerate(cases):
            case_lookup[(key, ci)] = case

    for entry in entries:
        if entry.requirement_key not in req_meta:
            raise ValueError(
                f"Manual review entry '{entry.requirement_key}' not found in generated_cases.json"
            )
        max_ci = req_case_counts[entry.requirement_key]
        for case_entry in entry.cases:
            if case_entry.case_index < 0 or case_entry.case_index >= max_ci:
                raise ValueError(
                    f"Manual review entry '{entry.requirement_key}' "
                    f"case_index={case_entry.case_index} out of range "
                    f"(0-{max_ci - 1}, {max_ci} case(s) total)"
                )

    weighted_scores: list[float] = []
    dim_scores: dict[str, list[float]] = defaultdict(list)
    dim_mins: dict[str, list[int]] = defaultdict(list)
    unacceptable: list[dict] = []
    requirement_details: list[dict] = []
    entry_details: list[dict] = []

    for entry in entries:
        ws = compute_weighted_score(entry)
        weighted_scores.append(ws)
        dim_scores["coverage_value"].append(entry.coverage_value)
        dim_mins["coverage_value"].append(entry.coverage_value)
        for dim in CASE_LEVEL_DIMS:
            dim_scores[dim].append(_avg_case_dim(entry, dim))
            dim_mins[dim].append(_min_case_dim(entry, dim))

        expected = req_meta.get(entry.requirement_key)
        req_unacceptable = False
        req_reasons: list[str] = []
        req_warnings: list[str] = []

        for case_entry in entry.cases:
            case = case_lookup.get((entry.requirement_key, case_entry.case_index))
            gate = apply_hard_gates(case_entry, case, expected)
            case_title = case.get("title", "")[:80] if case else "(not found)"

            detail = {
                "requirement_key": entry.requirement_key,
                "case_index": case_entry.case_index,
                "case_title": case_title,
                "requirement_alignment": case_entry.requirement_alignment,
                "executability": case_entry.executability,
                "observability": case_entry.observability,
                "pass_fail_clarity": case_entry.pass_fail_clarity,
                "information_integrity": case_entry.information_integrity,
                "state_and_environment_control": case_entry.state_and_environment_control,
                "automation_readiness": case_entry.automation_readiness,
                "coverage_value": entry.coverage_value,
                "requirement_weighted_score": ws,
                "unacceptable": gate.unacceptable,
                "unacceptable_reasons": gate.reasons,
                "warnings": gate.warnings,
                "reviewer": case_entry.reviewer or entry.reviewer,
                "notes": case_entry.notes,
            }
            if gate.unacceptable:
                req_unacceptable = True
                req_reasons.extend(gate.reasons)
                unacceptable.append(detail)
            req_warnings.extend(gate.warnings)
            entry_details.append(detail)

        requirement_details.append({
            "requirement_key": entry.requirement_key,
            "coverage_value": entry.coverage_value,
            "case_count": len(entry.cases),
            "weighted_score": ws,
            "case_dimension_averages": {
                dim: round(_avg_case_dim(entry, dim), 1) for dim in CASE_LEVEL_DIMS
            },
            "case_dimension_mins": {
                dim: _min_case_dim(entry, dim) for dim in CASE_LEVEL_DIMS
            },
            "unacceptable": req_unacceptable,
            "unacceptable_reasons": sorted(set(req_reasons)),
            "warnings": sorted(set(req_warnings)),
            "reviewer": entry.reviewer,
            "notes": entry.notes,
        })

    avg_weighted = round(sum(weighted_scores) / len(weighted_scores), 1) if weighted_scores else 0
    dim_avg = {
        dim: round(sum(vals) / len(vals), 1) if vals else 0
        for dim, vals in dim_scores.items()
    }
    dim_min = {
        dim: min(vals) if vals else 0
        for dim, vals in dim_mins.items()
    }

    buckets = {"0-1": 0, "1-2": 0, "2-3": 0, "3-4": 0, "4-5": 0}
    for ws in weighted_scores:
        if ws < 1:
            buckets["0-1"] += 1
        elif ws < 2:
            buckets["1-2"] += 1
        elif ws < 3:
            buckets["2-3"] += 1
        elif ws < 4:
            buckets["3-4"] += 1
        else:
            buckets["4-5"] += 1

    return {
        "average_weighted_score": avg_weighted,
        "dimension_averages": dim_avg,
        "dimension_mins": dim_min,
        "unacceptable": unacceptable,
        "score_distribution": buckets,
        "requirement_details": requirement_details,
        "entry_details": entry_details,
        "total_requirements": len(entries),
        "total_cases": sum(len(e.cases) for e in entries),
        "total_entries": sum(len(e.cases) for e in entries),
        "total_unacceptable": len(unacceptable),
        "weights": _WEIGHTS,
    }
