"""Manual Review Score — human-scored rubric for generated test cases.

Weighted score formula (from docs/prompt-quality-optimization.md):

    weighted = 0.20 * executability
             + 0.20 * observability
             + 0.20 * coverage_value
             + 0.40 * missing_information_detection

Hard gates (applied before accepting any weighted score):

- missing_information_detection < 3 → unacceptable
- Case should contain [NEEDS REVIEW] but does not → unacceptable
- Case invents missing signal/threshold/timing/state/observation → unacceptable
- Semantically complete requirement adds unnecessary [NEEDS REVIEW] →
  penalty/warning, not automatic severe unless blocks executability

[NEEDS REVIEW] only covers: signal, threshold, timing, state, observation.
It does NOT cover HIL channel names, tool commands, or bench configuration.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_VALID_SCORES = {1, 2, 3, 4, 5}
_WEIGHTS = {
    "executability": 0.20,
    "observability": 0.20,
    "coverage_value": 0.20,
    "missing_information_detection": 0.40,
}


@dataclass
class ReviewEntry:
    requirement_key: str
    case_index: int  # 0-based index into generated_cases.json case list
    executability: int
    observability: int
    coverage_value: int
    missing_information_detection: int
    reviewer: str = ""
    notes: str = ""


@dataclass
class HardGateResult:
    unacceptable: bool = False
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_review_scores(path: str | Path) -> list[ReviewEntry]:
    """Load and validate a manual_review_scores.json file.

    Raises ValueError on schema or score-range errors.
    """
    path = Path(path)
    if not path.exists():
        raise ValueError(f"Review file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Review file is not valid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError("Review file must contain a JSON array of review entries")

    entries: list[ReviewEntry] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Entry {i} is not a JSON object")

        key = item.get("requirement_key")
        if not isinstance(key, str) or not key.strip():
            raise ValueError(f"Entry {i}: missing or empty 'requirement_key'")

        ci = item.get("case_index")
        if not isinstance(ci, int) or ci < 0:
            raise ValueError(f"Entry {i} ('{key}'): 'case_index' must be a non-negative integer")

        fields = ["executability", "observability", "coverage_value", "missing_information_detection"]
        for fname in fields:
            val = item.get(fname)
            if val not in _VALID_SCORES:
                raise ValueError(
                    f"Entry {i} ('{key}'): '{fname}' must be 1-5, got {val!r}"
                )

        entries.append(ReviewEntry(
            requirement_key=key.strip(),
            case_index=ci,
            executability=item["executability"],
            observability=item["observability"],
            coverage_value=item["coverage_value"],
            missing_information_detection=item["missing_information_detection"],
            reviewer=item.get("reviewer", ""),
            notes=item.get("notes", ""),
        ))

    return entries


def compute_weighted_score(entry: ReviewEntry) -> float:
    """Compute the 0-5 weighted score for a review entry.

    20% executability + 20% observability + 20% coverage_value
    + 40% missing_information_detection.

    Rounded to 1 decimal place.
    """
    w = (
        _WEIGHTS["executability"] * entry.executability
        + _WEIGHTS["observability"] * entry.observability
        + _WEIGHTS["coverage_value"] * entry.coverage_value
        + _WEIGHTS["missing_information_detection"] * entry.missing_information_detection
    )
    return round(w, 1)


def apply_hard_gates(
    entry: ReviewEntry,
    generated_case: dict | None = None,
    expected_missing_categories: list[str] | None = None,
) -> HardGateResult:
    """Apply hard gates before accepting a weighted score.

    Requires:
    - entry: the manual review entry
    - generated_case: the matching case dict from generated_cases.json
    - expected_missing_categories: from the Prompt Evaluation Set entry
    """
    result = HardGateResult()

    # Gate 1: missing_information_detection < 3
    if entry.missing_information_detection < 3:
        result.unacceptable = True
        result.reasons.append(
            f"missing_information_detection={entry.missing_information_detection} (< 3)"
        )

    # Gates 2-4 require the generated case and expected_missing_categories
    if generated_case is None:
        return result

    steps = generated_case.get("steps", [])
    nr_in_steps = any(
        "[needs review]" in (s["action"] + str(s["expected"] or "")).lower()
        for s in steps
    )
    has_expected_missing = bool(expected_missing_categories)

    # Gate 2: case should contain [NEEDS REVIEW] but does not
    if has_expected_missing and not nr_in_steps:
        result.unacceptable = True
        result.reasons.append(
            f"Expected missing {expected_missing_categories} but case lacks [NEEDS REVIEW]"
        )

    # Gate 3: case invents missing semantics — heuristically: expected missing
    # is non-empty but case has numeric values without [NEEDS REVIEW]
    if has_expected_missing:
        for s in steps:
            text = f"{s['action']} {s['expected'] or ''}"
            import re
            if re.search(r"\d+\.?\d+", text) and "[needs review]" not in text.lower():
                result.unacceptable = True
                result.reasons.append(
                    "Case contains numeric value(s) that appear to invent "
                    "missing threshold/timing semantics"
                )
                break

    # Gate 4: semantically complete but unnecessary [NEEDS REVIEW] → warning
    if not has_expected_missing and nr_in_steps:
        result.warnings.append(
            "Requirement appears semantically complete but case contains "
            "[NEEDS REVIEW] — penalized but not automatically severe"
        )

    return result


# ── Summary helpers for report rendering ─────────────────────────────────


def get_review_summary(
    entries: list[ReviewEntry],
    generated_data: list[dict],
) -> dict:
    """Compute aggregate stats for the report.

    Returns a dict with:
    - average_weighted_score
    - dimension_averages (dict)
    - unacceptable (list of dicts with reason)
    - score_distribution (0-1, 1-2, 2-3, 3-4, 4-5 buckets)
    - entry_details (list of per-entry dicts for the report)
    """
    if not entries:
        return {}

    # Build lookup: (requirement_key, case_index) → case dict
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

    # Validate every review entry matches generated data
    for entry in entries:
        if entry.requirement_key not in req_meta:
            raise ValueError(
                f"Manual review entry '{entry.requirement_key}' "
                f"(case_index={entry.case_index}) not found in generated_cases.json"
            )
        max_ci = req_case_counts[entry.requirement_key]
        if entry.case_index < 0 or entry.case_index >= max_ci:
            raise ValueError(
                f"Manual review entry '{entry.requirement_key}' "
                f"case_index={entry.case_index} out of range "
                f"(0-{max_ci - 1}, {max_ci} case(s) total)"
            )

    weighted_scores: list[float] = []
    dim_scores: dict[str, list[int]] = defaultdict(list)
    unacceptable: list[dict] = []
    entry_details: list[dict] = []

    for entry in entries:
        ws = compute_weighted_score(entry)
        weighted_scores.append(ws)

        for dim in ["executability", "observability", "coverage_value", "missing_information_detection"]:
            dim_scores[dim].append(getattr(entry, dim))

        case = case_lookup.get((entry.requirement_key, entry.case_index))
        expected = req_meta.get(entry.requirement_key)
        gate = apply_hard_gates(entry, case, expected)

        detail = {
            "requirement_key": entry.requirement_key,
            "case_index": entry.case_index,
            "case_title": case.get("title", "")[:80] if case else "(not found)",
            "executability": entry.executability,
            "observability": entry.observability,
            "coverage_value": entry.coverage_value,
            "missing_information_detection": entry.missing_information_detection,
            "weighted_score": ws,
            "unacceptable": gate.unacceptable,
            "unacceptable_reasons": gate.reasons,
            "warnings": gate.warnings,
            "reviewer": entry.reviewer,
            "notes": entry.notes,
        }
        if gate.unacceptable:
            unacceptable.append(detail)
        entry_details.append(detail)

    avg_weighted = round(sum(weighted_scores) / len(weighted_scores), 1) if weighted_scores else 0
    dim_avg = {
        dim: round(sum(vals) / len(vals), 1) if vals else 0
        for dim, vals in dim_scores.items()
    }

    # Score distribution buckets
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
        "unacceptable": unacceptable,
        "score_distribution": buckets,
        "entry_details": entry_details,
        "total_entries": len(entries),
        "total_unacceptable": len(unacceptable),
    }
