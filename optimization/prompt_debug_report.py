"""Deterministic prompt debug report CLI.

Generates a Markdown prompt debug report from a completed evaluation round.
Must not call an LLM, modify prompt files, or choose a winning patch.

Usage:
    python -m optimization.prompt_debug_report --round-dir <path-to-round-dir>
    python -m optimization.prompt_debug_report --round-dir <path> --output <path>
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# ── Known checklist item descriptions ──────────────────────────────────────

KNOWN_ITEM_DESCRIPTIONS: dict[str, str] = {
    "2.1.1": "Known signal names referenced in cases match requirement wording; no unsupported signal-name variants.",
    "2.1.2": "No invented identifiers outside selected requirement or accepted test basis.",
    "3.2.1": "Missing signal/threshold/timing/state/observation must be marked with [NEEDS REVIEW].",
    "3.2.3": "Do not add unnecessary [NEEDS REVIEW] when requirement semantics are complete.",
    "3.3.2": "Missing timing placeholder should be placed in a standalone wait step.",
    "4.1.1": "Timing wait and execution action should be separate steps.",
    "4.1.4": "Action should not contain pass/fail judgment or intent narration.",
    "5.1.1": "normal_behavior case should describe normal functional trigger and response.",
}

VALID_CATEGORIES = {"signal", "threshold", "timing", "state", "observation"}

ALL_DIMENSIONS = [
    "requirement_alignment", "coverage_value", "executability", "observability",
    "pass_fail_clarity", "information_integrity", "state_and_environment_control",
    "automation_readiness",
]

DIMENSION_LABELS: dict[str, str] = {
    "requirement_alignment": "Requirement Alignment",
    "coverage_value": "Coverage Value",
    "executability": "Executability",
    "observability": "Observability",
    "pass_fail_clarity": "Pass/Fail Clarity",
    "information_integrity": "Information Integrity",
    "state_and_environment_control": "State & Environment Control",
    "automation_readiness": "Automation Readiness",
}


# ── Data loading ───────────────────────────────────────────────────────────


def load_round(round_dir: Path) -> dict[str, Any]:
    """Load all input files from a round directory.

    Returns a dict with keys: summary, generated_cases, hardrule_evaluation,
    deepseek_evaluation (may be None).
    """
    required = ["summary.json", "generated_cases.json", "hardrule_evaluation.json"]
    for filename in required:
        if not (round_dir / filename).exists():
            raise FileNotFoundError(f"Required file not found: {round_dir / filename}")

    with open(round_dir / "summary.json", encoding="utf-8") as f:
        summary = json.load(f)
    with open(round_dir / "generated_cases.json", encoding="utf-8") as f:
        generated_cases = json.load(f)
    with open(round_dir / "hardrule_evaluation.json", encoding="utf-8") as f:
        hardrule_evaluation = json.load(f)

    deepseek_evaluation = None
    ds_path = round_dir / "deepseek_evaluation.json"
    if ds_path.exists():
        with open(ds_path, encoding="utf-8") as f:
            deepseek_evaluation = json.load(f)

    return {
        "round_dir": str(round_dir),
        "summary": summary,
        "generated_cases": generated_cases,
        "hardrule_evaluation": hardrule_evaluation,
        "deepseek_evaluation": deepseek_evaluation,
    }


# ── Hard-Rule Fail Ranking ─────────────────────────────────────────────────


def compute_hardrule_fail_ranking(hardrule_eval: dict) -> list[tuple[str, int, str]]:
    """Sort item_fail_counts descending by fail count.

    Returns list of (item_id, fail_count, description).
    """
    item_fail_counts: dict[str, int] = hardrule_eval.get("item_fail_counts", {})
    ranking: list[tuple[str, int, str]] = []
    for item_id, count in sorted(item_fail_counts.items(), key=lambda x: -x[1]):
        desc = KNOWN_ITEM_DESCRIPTIONS.get(item_id, "(description not available)")
        ranking.append((item_id, count, desc))
    return ranking


# ── Requirements Where All Cases Failed ─────────────────────────────────────


def compute_all_fail_requirements(generated_cases: list, hardrule_eval: dict) -> dict:
    """Find requirements where every generated case failed hard rules.

    Returns dict with all_fail_requirements list and per-requirement breakdown.
    """
    # Group hardrule cases by requirement_key
    req_cases: dict[str, list[dict]] = defaultdict(list)
    for case in hardrule_eval.get("cases", []):
        req_cases[case["requirement_key"]].append(case)

    all_fail: list[dict] = []
    req_breakdown: list[dict] = []

    for req in generated_cases:
        req_key = req["requirement_key"]
        hr_cases = req_cases.get(req_key, [])
        total = len(req.get("cases", []))
        if total == 0:
            continue

        passed_count = 0
        failed_count = 0
        dominant_failures: Counter[str] = Counter()
        for hr_case in hr_cases:
            failed_items = [
                item["item_id"]
                for item in hr_case.get("items", [])
                if item.get("result") == "fail"
            ]
            if not failed_items:
                passed_count += 1
            else:
                failed_count += 1
                for item_id in failed_items:
                    dominant_failures[item_id] += 1

        entry = {
            "requirement_key": req_key,
            "evaluation_bucket": req.get("evaluation_bucket", ""),
            "total_cases": total,
            "passed_cases": passed_count,
            "failed_cases": failed_count,
            "dominant_failure_items": dominant_failures.most_common(5),
        }
        req_breakdown.append(entry)

        if passed_count == 0 and failed_count > 0:
            all_fail.append(entry)

    return {
        "all_fail_requirements": all_fail,
        "requirement_breakdown": req_breakdown,
    }


# ── Retry / Exhausted Summary ──────────────────────────────────────────────


def compute_retry_summary(generated_cases: list) -> dict:
    """Aggregate retry and exhausted counts from generated cases."""
    total_retried = 0
    total_exhausted = 0
    reqs_with_retries: set[str] = set()
    reqs_with_exhausted: set[str] = set()

    for req in generated_cases:
        req_key = req["requirement_key"]
        for case in req.get("cases", []):
            retry = case.get("retry", {})
            if not isinstance(retry, dict):
                continue
            attempts = retry.get("attempts", 0)
            exhausted = retry.get("exhausted", False)
            if attempts > 0:
                total_retried += 1
                reqs_with_retries.add(req_key)
            if exhausted:
                total_exhausted += 1
                reqs_with_exhausted.add(req_key)

    return {
        "total_retried": total_retried,
        "total_exhausted": total_exhausted,
        "reqs_with_retries": sorted(reqs_with_retries),
        "reqs_with_exhausted": sorted(reqs_with_exhausted),
    }


# ── Missing Category Mismatch Summary ──────────────────────────────────────


def compute_missing_category_mismatches(generated_cases: list) -> dict:
    """Compare expected_missing_categories vs actual missing_info_items categories."""
    total_with_expected = 0
    total_exact_matches = 0
    total_mismatches = 0
    mismatches: list[dict] = []
    bucket_mismatches: dict[str, dict] = defaultdict(lambda: {"count": 0, "mismatches": []})

    for req in generated_cases:
        expected = req.get("expected_missing_categories", [])
        if not expected:
            continue
        total_with_expected += 1

        actual_items = req.get("analysis", {}).get("missing_info_items", [])
        actual_cats = {
            mi["category"]
            for mi in actual_items
            if mi.get("category") and mi["category"].strip()
        }

        expected_set = set(expected)
        missing = sorted(expected_set - actual_cats)
        extra = sorted(actual_cats - expected_set)

        if not missing and not extra:
            total_exact_matches += 1
            continue

        total_mismatches += 1
        bucket = req.get("evaluation_bucket", "unknown")
        mismatch_entry = {
            "requirement_key": req["requirement_key"],
            "evaluation_bucket": bucket,
            "expected": sorted(expected_set),
            "actual": sorted(actual_cats),
            "missing_from_actual": missing,
            "extra_in_actual": extra,
        }
        mismatches.append(mismatch_entry)
        bucket_mismatches[bucket]["count"] += 1
        bucket_mismatches[bucket]["mismatches"].append(mismatch_entry)

    # Sort mismatches: prioritize missing_from_actual (false negatives)
    mismatches.sort(key=lambda m: (len(m["missing_from_actual"]) == 0, -len(m["missing_from_actual"]), m["requirement_key"]))

    return {
        "total_requirements_with_expected": total_with_expected,
        "total_exact_matches": total_exact_matches,
        "total_mismatches": total_mismatches,
        "mismatches": mismatches,
        "mismatches_by_bucket": dict(bucket_mismatches),
    }


# ── Case Count Distribution ────────────────────────────────────────────────


def compute_case_count_distribution(generated_cases: list, high_threshold: int = 5) -> dict:
    """Compute case count distribution per requirement."""
    counts: Counter[int] = Counter()
    req_counts: list[dict] = []
    total_cases = 0

    for req in generated_cases:
        n = len(req.get("cases", []))
        counts[n] += 1
        total_cases += n
        req_counts.append({
            "requirement_key": req["requirement_key"],
            "evaluation_bucket": req.get("evaluation_bucket", ""),
            "case_count": n,
            "is_high": n >= high_threshold,
        })

    num_reqs = len(generated_cases)
    avg = round(total_cases / num_reqs, 1) if num_reqs else 0

    high_count = [r for r in req_counts if r["is_high"]]
    high_count.sort(key=lambda r: -r["case_count"])

    return {
        "total_cases": total_cases,
        "total_requirements": num_reqs,
        "average_cases_per_req": avg,
        "distribution": dict(sorted(counts.items())),
        "high_count_requirements": high_count,
        "high_threshold": high_threshold,
    }


# ── DeepSeek Low Dimension Summary ─────────────────────────────────────────


def compute_deepseek_summary(deepseek_eval: dict | None, generated_cases: list) -> dict:
    """Extract DeepSeek evaluation metrics if available."""
    if deepseek_eval is None:
        return {"available": False}

    dim_avgs = deepseek_eval.get("dimension_averages", {})
    low_dims = {
        dim: avg
        for dim, avg in dim_avgs.items()
        if isinstance(avg, (int, float)) and avg < 3.0
    }

    # Worst requirements by weighted score (lowest 10)
    reqs = deepseek_eval.get("requirements", [])
    worst_reqs = sorted(reqs, key=lambda r: r.get("weighted_score", 5.0))[:10]
    worst_req_entries = [
        {
            "requirement_key": r["requirement_key"],
            "weighted_score": r.get("weighted_score", 0),
            "coverage_value": r.get("coverage_value", 0),
        }
        for r in worst_reqs
    ]

    # Unscored requirements
    scored_keys = {r["requirement_key"] for r in reqs}
    gen_keys = {req["requirement_key"] for req in generated_cases if req.get("cases")}
    unscored = sorted(gen_keys - scored_keys)

    # Build per-requirement lookup for DeepSeek scores
    ds_req_lookup: dict[str, dict] = {}
    for r in reqs:
        ds_req_lookup[r["requirement_key"]] = r

    return {
        "available": True,
        "overall_weighted": deepseek_eval.get("overall_weighted", 0),
        "total_requirements_evaluated": deepseek_eval.get("total_requirements", 0),
        "errors": deepseek_eval.get("errors", 0),
        "dimension_averages": dim_avgs,
        "low_dimensions": low_dims,
        "worst_requirements": worst_req_entries,
        "unscored_requirements": unscored,
        "ds_req_lookup": ds_req_lookup,
    }


# ── Failure Clusters ───────────────────────────────────────────────────────


def detect_failure_clusters(data: dict) -> list[dict]:
    """Generate deterministic failure clusters from available signals."""
    generated: list = data["generated_cases"]
    hardrule: dict = data["hardrule_evaluation"]
    ds_summary: dict = data.get("_ds_summary", {})

    item_fails: dict[str, int] = hardrule.get("item_fail_counts", {})
    clusters: list[dict] = []

    # Helper: find affected requirements for a given item_id
    def _affected_reqs_for_item(item_id: str) -> set[str]:
        affected: set[str] = set()
        for case in hardrule.get("cases", []):
            for item in case.get("items", []):
                if item.get("item_id") == item_id and item.get("result") == "fail":
                    affected.add(case["requirement_key"])
                    break
        return affected

    # Helper: count affected cases for a given item_id
    def _affected_case_count(item_id: str) -> int:
        return item_fails.get(item_id, 0)

    # Helper: severity from count
    def _severity(count: int, total_cases: int) -> str:
        if total_cases == 0:
            return "low"
        rate = count / total_cases
        if rate > 0.15:
            return "high"
        if rate > 0.05:
            return "medium"
        return "low"

    total_cases = hardrule.get("total_cases", 1)

    # ── missing_info_false_negative ────────────────────────────────────
    fn_item_fails = item_fails.get("3.2.1", 0)
    fn_reqs = _affected_reqs_for_item("3.2.1")

    # Also detect from mismatches where expected missing not in actual
    mm_data: dict = data.get("_category_mismatches", {})
    for m in mm_data.get("mismatches", []):
        if m["missing_from_actual"]:
            fn_reqs.add(m["requirement_key"])

    if fn_reqs or fn_item_fails > 0:
        clusters.append({
            "id": "missing_info_false_negative",
            "title": "Missing Information False Negatives",
            "severity": _severity(fn_item_fails, total_cases),
            "philosophy_principle": "Missing Information Philosophy, Information Integrity",
            "related_hardrule_items": ["3.2.1"],
            "related_deepseek_dimensions": ["information_integrity"],
            "affected_requirements": sorted(fn_reqs),
            "affected_case_count": fn_item_fails,
            "evidence_summary": (
                f"{fn_item_fails} case(s) across {len(fn_reqs)} requirement(s) "
                f"failed 3.2.1: expected [NEEDS REVIEW] markers are missing. "
                "The model may be inventing concrete values where requirement semantics are incomplete."
            ),
            "representative_cases": [],
            "opposite_failure_risk": (
                "Over-correcting may cause 3.2.3 (unnecessary [NEEDS REVIEW]) "
                "by marking semantically complete requirement behavior."
            ),
        })

    # ── missing_info_false_positive ────────────────────────────────────
    fp_item_fails = item_fails.get("3.2.3", 0)
    fp_reqs = _affected_reqs_for_item("3.2.3")

    # Also detect from mismatches where extra in actual
    for m in mm_data.get("mismatches", []):
        if m["extra_in_actual"]:
            fp_reqs.add(m["requirement_key"])

    if fp_reqs or fp_item_fails > 0:
        clusters.append({
            "id": "missing_info_false_positive",
            "title": "Missing Information False Positives (Unnecessary [NEEDS REVIEW])",
            "severity": _severity(fp_item_fails, total_cases),
            "philosophy_principle": "Missing Information Philosophy, Anti-Patterns",
            "related_hardrule_items": ["3.2.3"],
            "related_deepseek_dimensions": ["information_integrity", "executability"],
            "affected_requirements": sorted(fp_reqs),
            "affected_case_count": fp_item_fails,
            "evidence_summary": (
                f"{fp_item_fails} case(s) across {len(fp_reqs)} requirement(s) "
                f"failed 3.2.3: unnecessary [NEEDS REVIEW] where requirement "
                "semantics are complete. The model may be over-marking uncertainties."
            ),
            "representative_cases": [],
            "opposite_failure_risk": (
                "Removing [NEEDS REVIEW] markers aggressively could cause 3.2.1 "
                "(missing markers where genuinely needed)."
            ),
        })

    # ── action_judgment_mixing ─────────────────────────────────────────
    aj_item_fails = item_fails.get("4.1.4", 0)
    aj_reqs = _affected_reqs_for_item("4.1.4")
    if aj_reqs or aj_item_fails > 0:
        clusters.append({
            "id": "action_judgment_mixing",
            "title": "Action/Judgment Mixing",
            "severity": _severity(aj_item_fails, total_cases),
            "philosophy_principle": "Action and Expected Boundary",
            "related_hardrule_items": ["4.1.4"],
            "related_deepseek_dimensions": ["executability", "pass_fail_clarity"],
            "affected_requirements": sorted(aj_reqs),
            "affected_case_count": aj_item_fails,
            "evidence_summary": (
                f"{aj_item_fails} case(s) across {len(aj_reqs)} requirement(s) "
                f"failed 4.1.4: pass/fail judgment or intent narration in action steps. "
                "The model may be conflating action execution with verification."
            ),
            "representative_cases": [],
            "opposite_failure_risk": (
                "Stricter action/expected separation may produce mechanical "
                "step splitting without improving test value."
            ),
        })

    # ── wait_action_not_separated ──────────────────────────────────────
    wa_item_fails = item_fails.get("4.1.1", 0) + item_fails.get("3.3.2", 0)
    wa_reqs = _affected_reqs_for_item("4.1.1") | _affected_reqs_for_item("3.3.2")
    if wa_reqs or wa_item_fails > 0:
        clusters.append({
            "id": "wait_action_not_separated",
            "title": "Wait/Action Not Separated",
            "severity": _severity(wa_item_fails, total_cases),
            "philosophy_principle": "Action and Expected Boundary, Executability Philosophy",
            "related_hardrule_items": ["4.1.1", "3.3.2"],
            "related_deepseek_dimensions": ["executability"],
            "affected_requirements": sorted(wa_reqs),
            "affected_case_count": wa_item_fails,
            "evidence_summary": (
                f"{item_fails.get('4.1.1', 0)} case(s) failed 4.1.1 (stimulus and "
                f"response not separated); {item_fails.get('3.3.2', 0)} case(s) "
                f"failed 3.3.2 (missing timing not in dedicated Wait step)."
            ),
            "representative_cases": [],
            "opposite_failure_risk": (
                "Over-separating steps may produce verbose case structures "
                "that are harder to review."
            ),
        })

    # ── case_count_inflation ───────────────────────────────────────────
    case_dist: dict = data.get("_case_distribution", {})
    high_reqs: list[dict] = case_dist.get("high_count_requirements", [])
    if high_reqs:
        ci_reqs = [r["requirement_key"] for r in high_reqs]
        clusters.append({
            "id": "case_count_inflation",
            "title": "Case Count Inflation",
            "severity": "high" if len(high_reqs) > 3 else "medium",
            "philosophy_principle": "Case Splitting Philosophy, Coverage Value",
            "related_hardrule_items": [],
            "related_deepseek_dimensions": ["coverage_value"],
            "affected_requirements": ci_reqs,
            "affected_case_count": sum(r["case_count"] for r in high_reqs),
            "evidence_summary": (
                f"{len(high_reqs)} requirement(s) generated >= 5 cases each "
                f"({', '.join(f'{r['requirement_key']}({r['case_count']})' for r in high_reqs)}). "
                "The model may be splitting cases without distinct verification value."
            ),
            "representative_cases": [],
            "opposite_failure_risk": (
                "Aggressively limiting case count may suppress legitimate "
                "boundary or diagnostic cases."
            ),
        })

    # ── low_executability ──────────────────────────────────────────────
    if ds_summary.get("available"):
        ex_avg = ds_summary.get("dimension_averages", {}).get("executability", 5.0)
        if isinstance(ex_avg, (int, float)) and ex_avg < 3.0:
            # Find requirements with low executability
            ex_reqs: list[str] = []
            for req in ds_summary.get("worst_requirements", []):
                ds_lookup = ds_summary.get("ds_req_lookup", {}).get(req["requirement_key"], {})
                case_avgs = ds_lookup.get("case_dimension_averages", {})
                if case_avgs.get("executability", 5) < 3.0:
                    ex_reqs.append(req["requirement_key"])

            clusters.append({
                "id": "low_executability",
                "title": "Low Executability",
                "severity": "high" if ex_avg < 2.5 else "medium",
                "philosophy_principle": "Executability Philosophy",
                "related_hardrule_items": [],
                "related_deepseek_dimensions": ["executability"],
                "affected_requirements": ex_reqs[:10],
                "affected_case_count": 0,
                "evidence_summary": (
                    f"DeepSeek executability average is {ex_avg:.1f} (below 3.0). "
                    f"Steps may be too abstract, multi-action, or depend on hidden assumptions."
                ),
                "representative_cases": [],
                "opposite_failure_risk": (
                    "Over-specifying steps may add pseudo-specific details "
                    "not in the test basis."
                ),
            })

    # ── low_automation_readiness ───────────────────────────────────────
    if ds_summary.get("available"):
        ar_avg = ds_summary.get("dimension_averages", {}).get("automation_readiness", 5.0)
        if isinstance(ar_avg, (int, float)) and ar_avg < 3.0:
            ar_reqs: list[str] = []
            for req in ds_summary.get("worst_requirements", []):
                ds_lookup = ds_summary.get("ds_req_lookup", {}).get(req["requirement_key"], {})
                case_avgs = ds_lookup.get("case_dimension_averages", {})
                if case_avgs.get("automation_readiness", 5) < 3.0:
                    ar_reqs.append(req["requirement_key"])

            clusters.append({
                "id": "low_automation_readiness",
                "title": "Low Automation Readiness",
                "severity": "high" if ar_avg < 2.5 else "medium",
                "philosophy_principle": "Executability Philosophy, Coverage Value",
                "related_hardrule_items": [],
                "related_deepseek_dimensions": ["automation_readiness"],
                "affected_requirements": ar_reqs[:10],
                "affected_case_count": 0,
                "evidence_summary": (
                    f"DeepSeek automation_readiness average is {ar_avg:.1f} (below 3.0). "
                    "Cases may be formally structured but hard to convert into executable test assets."
                ),
                "representative_cases": [],
                "opposite_failure_risk": (
                    "Over-focusing on automation readiness may sacrifice "
                    "natural-language requirement clarity."
                ),
            })

    return clusters


# ── Philosophy Regression Checks ───────────────────────────────────────────


def check_philosophy_regressions(data: dict) -> list[dict]:
    """Check for philosophy regression risks based on available evidence."""
    hardrule: dict = data["hardrule_evaluation"]
    ds_summary: dict = data.get("_ds_summary", {})
    case_dist: dict = data.get("_case_distribution", {})
    item_fails: dict[str, int] = hardrule.get("item_fail_counts", {})

    checks: list[dict] = []

    # ── [NEEDS REVIEW] misuse risk ─────────────────────────────────────
    nr_risk_items = ["3.2.1", "3.2.3"]
    nr_failures = sum(item_fails.get(i, 0) for i in nr_risk_items)
    checks.append({
        "check": "[NEEDS REVIEW] misuse risk",
        "status": "observed" if nr_failures > 0 else "not_detected",
        "evidence": f"{nr_failures} combined failures on items {nr_risk_items}" if nr_failures else "",
        "source": "hardrule",
    })

    # ── Action/expected boundary risk ──────────────────────────────────
    boundary_items = ["4.1.1", "4.1.4", "3.3.2"]
    boundary_failures = sum(item_fails.get(i, 0) for i in boundary_items)
    checks.append({
        "check": "Action/expected boundary risk",
        "status": "observed" if boundary_failures > 0 else "not_detected",
        "evidence": f"{boundary_failures} combined failures on items {boundary_items}" if boundary_failures else "",
        "source": "hardrule",
    })

    # ── Coverage volume risk ───────────────────────────────────────────
    high_count = case_dist.get("high_count_requirements", [])
    checks.append({
        "check": "Coverage volume risk",
        "status": "observed" if high_count else "not_detected",
        "evidence": f"{len(high_count)} requirement(s) with case_count >= {case_dist.get('high_threshold', 5)}"
                     if high_count else "",
        "source": "generated_cases",
    })

    # ── Executability risk ─────────────────────────────────────────────
    if ds_summary.get("available"):
        ex_avg = ds_summary.get("dimension_averages", {}).get("executability", 5.0)
        checks.append({
            "check": "Executability risk",
            "status": "observed" if isinstance(ex_avg, (int, float)) and ex_avg < 3.0 else "not_detected",
            "evidence": f"DeepSeek executability average: {ex_avg}" if isinstance(ex_avg, (int, float)) else "",
            "source": "deepseek",
        })
    else:
        checks.append({
            "check": "Executability risk",
            "status": "possible",
            "evidence": "DeepSeek evaluation not available",
            "source": "insufficient_data",
        })

    # ── Metric-gaming risk ─────────────────────────────────────────────
    if ds_summary.get("available"):
        ex_avg = ds_summary.get("dimension_averages", {}).get("executability", 5.0)
        cov_avg = ds_summary.get("dimension_averages", {}).get("coverage_value", 5.0)
        has_high_count = bool(high_count)
        if has_high_count and isinstance(ex_avg, (int, float)) and ex_avg < 3.0:
            checks.append({
                "check": "Metric-gaming risk",
                "status": "possible",
                "evidence": (
                    f"High case count ({len(high_count)} reqs >= 5 cases) coexists with "
                    f"low executability ({ex_avg}) or coverage ({cov_avg})"
                ),
                "source": "hardrule+deepseek",
            })
        else:
            checks.append({
                "check": "Metric-gaming risk",
                "status": "not_detected",
                "evidence": "",
                "source": "hardrule+deepseek",
            })
    else:
        checks.append({
            "check": "Metric-gaming risk",
            "status": "possible" if high_count else "not_detected",
            "evidence": "DeepSeek not available; high case count observed" if high_count else "",
            "source": "hardrule",
        })

    # ── Information honesty risk ───────────────────────────────────────
    honesty_items = ["2.1.1", "2.1.2", "3.2.1"]
    honesty_failures = sum(item_fails.get(i, 0) for i in honesty_items)
    checks.append({
        "check": "Information honesty risk",
        "status": "observed" if honesty_failures > 0 else "not_detected",
        "evidence": f"{honesty_failures} combined failures on items {honesty_items}" if honesty_failures else "",
        "source": "hardrule",
    })

    # ── Traceability risk ──────────────────────────────────────────────
    if ds_summary.get("available"):
        ra_avg = ds_summary.get("dimension_averages", {}).get("requirement_alignment", 5.0)
        checks.append({
            "check": "Traceability risk",
            "status": "observed" if isinstance(ra_avg, (int, float)) and ra_avg < 3.0 else "not_detected",
            "evidence": f"DeepSeek requirement_alignment average: {ra_avg}",
            "source": "deepseek",
        })
    else:
        checks.append({
            "check": "Traceability risk",
            "status": "insufficient_data",
            "evidence": "DeepSeek evaluation not available",
            "source": "insufficient_data",
        })

    # ── Natural-language preservation risk ─────────────────────────────
    checks.append({
        "check": "Natural-language preservation risk",
        "status": "insufficient_data",
        "evidence": "v1 does not implement bare marker detection for natural-language preservation",
        "source": "insufficient_data",
    })

    return checks


# ── Representative Cases ───────────────────────────────────────────────────


def select_representative_cases(data: dict) -> list[dict]:
    """Select deterministic representative cases for human review.

    Prefers: all-fail requirements, retry exhausted, high-severity cluster cases,
    worst DeepSeek requirements, cases with multiple hard-rule failures.
    Limit to ~10.
    """
    generated: list = data["generated_cases"]
    hardrule: dict = data["hardrule_evaluation"]
    ds_summary: dict = data.get("_ds_summary", {})
    all_fail: dict = data.get("_all_fail", {})
    retry_summary: dict = data.get("_retry_summary", {})
    clusters: list = data.get("_clusters", [])

    hr_cases_lookup: dict[tuple[str, int], dict] = {}
    for case in hardrule.get("cases", []):
        hr_cases_lookup[(case["requirement_key"], case["case_index"])] = case

    ds_case_lookup: dict[tuple[str, int], dict] = {}
    if ds_summary.get("available"):
        for req in ds_summary.get("ds_req_lookup", {}).values():
            for case in req.get("cases", []):
                key = (case["requirement_key"], case["case_index"])
                ds_case_lookup[key] = case

    # Selection pools
    pool_all_fail: list[dict] = []
    pool_retry_exhausted: list[dict] = []
    pool_high_severity: list[dict] = []
    pool_worst_ds: list[dict] = []
    pool_multi_fail: list[dict] = []

    all_fail_keys = {r["requirement_key"] for r in all_fail.get("all_fail_requirements", [])}
    exhausted_keys = set(retry_summary.get("reqs_with_exhausted", []))

    # High-severity cluster requirement keys
    high_sev_req_keys: set[str] = set()
    for cluster in clusters:
        if cluster.get("severity") == "high":
            high_sev_req_keys.update(cluster.get("affected_requirements", []))

    # Worst DS requirement keys
    worst_ds_keys = {r["requirement_key"] for r in ds_summary.get("worst_requirements", [])}

    selected: list[dict] = []
    selected_keys: set[tuple[str, int]] = set()

    def _build_case_entry(req_key: str, case_idx: int, case_data: dict, reason: str, cluster_ids: list[str]) -> dict:
        hr_case = hr_cases_lookup.get((req_key, case_idx), {})
        failed_items = [
            item["item_id"]
            for item in hr_case.get("items", [])
            if item.get("result") == "fail"
        ]

        retry = case_data.get("retry", {})
        retry_attempts = retry.get("attempts", 0) if isinstance(retry, dict) else 0
        retry_exhausted = retry.get("exhausted", False) if isinstance(retry, dict) else False

        ds_notes: list[str] = []
        ds_case = ds_case_lookup.get((req_key, case_idx))
        if ds_case:
            for dim in ALL_DIMENSIONS:
                note = ds_case.get(f"{dim}_note", "")
                if note and isinstance(note, str):
                    ds_notes.append(f"[{DIMENSION_LABELS.get(dim, dim)}] {note}")

        req_data = next((r for r in generated if r["requirement_key"] == req_key), {})

        return {
            "requirement_key": req_key,
            "evaluation_bucket": req_data.get("evaluation_bucket", ""),
            "case_index": case_idx,
            "case_title": case_data.get("title", ""),
            "selection_reason": reason,
            "cluster_ids": cluster_ids,
            "hardrule_failures": failed_items,
            "retry_attempts": retry_attempts,
            "retry_exhausted": retry_exhausted,
            "deepseek_notes": ds_notes[:3],  # Limit notes
        }

    def _add_case(req_key: str, case_idx: int, case_data: dict, reason: str,
                  cluster_ids: list[str] | None = None) -> bool:
        key = (req_key, case_idx)
        if key in selected_keys:
            return False
        entry = _build_case_entry(req_key, case_idx, case_data, reason, cluster_ids or [])
        selected.append(entry)
        selected_keys.add(key)
        return True

    # 1. All-fail requirements (up to 3)
    for req in all_fail.get("all_fail_requirements", []):
        req_key = req["requirement_key"]
        req_data = next((r for r in generated if r["requirement_key"] == req_key), None)
        if not req_data:
            continue
        cases = req_data.get("cases", [])
        if cases:
            _add_case(req_key, 0, cases[0],
                      f"From requirement where all {len(cases)} cases failed hard rules")

    # 2. Retry exhausted (up to 3)
    for req in generated:
        req_key = req["requirement_key"]
        if req_key not in exhausted_keys:
            continue
        for ci, case in enumerate(req.get("cases", [])):
            retry = case.get("retry", {})
            if isinstance(retry, dict) and retry.get("exhausted"):
                if _add_case(req_key, ci, case,
                             f"Retry exhausted after {retry.get('attempts', 0)} attempts"):
                    break

    # 3. High-severity cluster cases (up to 2)
    for req in generated:
        req_key = req["requirement_key"]
        if req_key not in high_sev_req_keys:
            continue
        hr_cases_for_req = [
            c for c in hardrule.get("cases", [])
            if c["requirement_key"] == req_key
        ]
        # Pick a case with most failures
        best_case = None
        best_fail_count = -1
        for hr_case in hr_cases_for_req:
            fail_count = sum(1 for item in hr_case.get("items", []) if item.get("result") == "fail")
            if fail_count > best_fail_count:
                best_fail_count = fail_count
                best_case = hr_case

        if best_case and best_fail_count > 0:
            case_idx = best_case["case_index"]
            case_data = req.get("cases", [])[case_idx] if case_idx < len(req.get("cases", [])) else {}
            # Find which cluster this belongs to
            cluster_ids_for_req = [
                c["id"] for c in clusters
                if req_key in c.get("affected_requirements", [])
            ]
            if _add_case(req_key, case_idx, case_data,
                         f"High-severity cluster case with {best_fail_count} hard-rule failures",
                         cluster_ids_for_req):
                pass

    # 4. Worst DeepSeek requirements (up to 2)
    for req in ds_summary.get("worst_requirements", [])[:5]:
        req_key = req["requirement_key"]
        req_data = next((r for r in generated if r["requirement_key"] == req_key), None)
        if not req_data:
            continue
        cases = req_data.get("cases", [])
        if cases:
            _add_case(req_key, 0, cases[0],
                      f"Lowest DeepSeek weighted score: {req.get('weighted_score', '?')}")

    # 5. Cases with multiple hard-rule failures (fill remaining up to ~10)
    for req in generated:
        req_key = req["requirement_key"]
        hr_cases_for_req = sorted(
            [c for c in hardrule.get("cases", []) if c["requirement_key"] == req_key],
            key=lambda c: -sum(1 for item in c.get("items", []) if item.get("result") == "fail"),
        )
        if hr_cases_for_req:
            best = hr_cases_for_req[0]
            fail_count = sum(1 for item in best.get("items", []) if item.get("result") == "fail")
            if fail_count >= 2:
                case_idx = best["case_index"]
                case_data = req.get("cases", [])[case_idx] if case_idx < len(req.get("cases", [])) else {}
                if len(selected) < 10:
                    _add_case(req_key, case_idx, case_data,
                              f"Multiple hard-rule failures ({fail_count} items)")

    return selected[:10]


# ── Report Rendering ───────────────────────────────────────────────────────


def generate_report(data: dict) -> str:
    """Generate the full Markdown prompt debug report."""
    # Pre-compute all intermediate data
    data["_hardrule_ranking"] = compute_hardrule_fail_ranking(data["hardrule_evaluation"])
    data["_all_fail"] = compute_all_fail_requirements(
        data["generated_cases"], data["hardrule_evaluation"]
    )
    data["_retry_summary"] = compute_retry_summary(data["generated_cases"])
    data["_category_mismatches"] = compute_missing_category_mismatches(data["generated_cases"])
    data["_case_distribution"] = compute_case_count_distribution(data["generated_cases"])
    data["_ds_summary"] = compute_deepseek_summary(
        data["deepseek_evaluation"], data["generated_cases"]
    )
    data["_clusters"] = detect_failure_clusters(data)
    data["_regressions"] = check_philosophy_regressions(data)
    data["_representative_cases"] = select_representative_cases(data)

    lines: list[str] = []
    _render_executive_summary(data, lines)
    _render_run_metrics(data, lines)
    _render_failure_clusters(data, lines)
    _render_philosophy_regressions(data, lines)
    _render_representative_cases(data, lines)
    _render_root_cause_hypotheses(data, lines)
    _render_patch_candidates(data, lines)
    _render_human_review_checklist(data, lines)

    return "\n".join(lines) + "\n"


def _render_executive_summary(data: dict, lines: list[str]) -> None:
    """Render the executive summary section."""
    summary: dict = data["summary"]
    hardrule: dict = data["hardrule_evaluation"]
    ds_summary: dict = data.get("_ds_summary", {})
    clusters: list = data.get("_clusters", [])
    regressions: list = data.get("_regressions", [])

    total_reqs = summary.get("total_requirements", 0)
    total_cases = summary.get("total_cases", 0)
    pass_rate = hardrule.get("case_pass_rate", 0)

    high_sev = [c["title"] for c in clusters if c.get("severity") == "high"]
    observed_regressions = [r for r in regressions if r["status"] == "observed"]

    ds_line = ""
    if ds_summary.get("available"):
        ds_line = f"DeepSeek weighted score: **{ds_summary['overall_weighted']:.1f}**"

    lines.extend([
        "# Prompt Debug Report",
        "",
        "## Executive Summary",
        "",
        f"- **{total_reqs}** requirements → **{total_cases}** generated cases",
        f"- Hard-rule case pass rate: **{pass_rate}%**",
        f"- {ds_line}" if ds_line else f"- DeepSeek evaluation: **not available**",
        "",
    ])

    if high_sev:
        lines.append(f"- **High-severity clusters**: {', '.join(high_sev)}")
    else:
        lines.append("- No high-severity failure clusters detected.")

    if observed_regressions:
        lines.append(f"- **Observed philosophy regressions**: {', '.join(r['check'] for r in observed_regressions)}")
    else:
        lines.append("- No philosophy regressions observed.")

    # Suitability assessment
    issues_count = len(high_sev) + len(observed_regressions)
    if issues_count == 0:
        lines.append("- Run appears suitable for prompt patch review.")
    elif issues_count <= 2:
        lines.append("- Run is suitable for prompt patch review with targeted fixes.")
    else:
        lines.append("- Run has multiple issues; prioritize high-severity clusters first.")

    lines.append("")


def _render_run_metrics(data: dict, lines: list[str]) -> None:
    """Render the run metrics section with all sub-sections."""
    summary: dict = data["summary"]
    hardrule: dict = data["hardrule_evaluation"]
    ds_summary: dict = data.get("_ds_summary", {})

    lines.extend([
        "## Run Metrics",
        "",
        "### Overview",
        "",
        f"| Metric | Value |",
        f"| --- | --- |",
        f"| Total requirements | {summary.get('total_requirements', 0)} |",
        f"| Total generated cases | {summary.get('total_cases', 0)} |",
        f"| Hard-rule total passed | {hardrule.get('total_passed', 0)} |",
        f"| Hard-rule total failed | {hardrule.get('total_cases', 0) - hardrule.get('total_passed', 0)} |",
        f"| Hard-rule case pass rate | **{hardrule.get('case_pass_rate', 0)}%** |",
        f"| Pipeline errors | {summary.get('errors', 0)} |",
    ])

    # Retry/Exhausted
    retry: dict = data.get("_retry_summary", {})
    lines.extend([
        f"| Retried cases | {retry.get('total_retried', 0)} |",
        f"| Exhausted cases | {retry.get('total_exhausted', 0)} |",
    ])

    # DeepSeek
    if ds_summary.get("available"):
        lines.extend([
            f"| DeepSeek requirements evaluated | {ds_summary.get('total_requirements_evaluated', 0)} |",
            f"| DeepSeek errors | {ds_summary.get('errors', 0)} |",
            f"| DeepSeek overall weighted score | **{ds_summary.get('overall_weighted', 0):.1f}** |",
        ])
    else:
        lines.append(f"| DeepSeek | not available |")

    lines.append("")

    # ── Hard-Rule Fail Ranking ─────────────────────────────────────────
    ranking: list = data.get("_hardrule_ranking", [])
    lines.extend([
        "### Hard-Rule Fail Ranking",
        "",
        "| Rank | Item ID | Fail Count | Description |",
        "| --- | --- | --- | --- |",
    ])
    if ranking:
        for i, (item_id, count, desc) in enumerate(ranking, 1):
            lines.append(f"| {i} | {item_id} | {count} | {desc} |")
    else:
        lines.append("| — | — | 0 | No hard-rule failures |")
    lines.append("")

    # ── Requirements Where All Cases Failed ────────────────────────────
    all_fail: dict = data.get("_all_fail", {})
    all_fail_reqs = all_fail.get("all_fail_requirements", [])
    lines.extend([
        "### Requirements Where All Cases Failed Hard Rules",
        "",
    ])
    if all_fail_reqs:
        lines.extend([
            "| Requirement | Bucket | Total Cases | Dominant Failures |",
            "| --- | --- | --- | --- |",
        ])
        for r in all_fail_reqs:
            dom = ", ".join(f"{item}({count})" for item, count in r["dominant_failure_items"])
            lines.append(
                f"| {r['requirement_key']} | {r['evaluation_bucket']} | "
                f"{r['total_cases']} | {dom} |"
            )
    else:
        lines.append("No requirements where all cases failed.")
    lines.append("")

    # ── Retry / Exhausted Summary ──────────────────────────────────────
    lines.extend([
        "### Retry / Exhausted Summary",
        "",
        f"- Total retried cases: **{retry.get('total_retried', 0)}**",
        f"- Total exhausted cases: **{retry.get('total_exhausted', 0)}**",
    ])
    if retry.get("reqs_with_retries"):
        lines.append(f"- Requirements with retried cases: {', '.join(retry['reqs_with_retries'])}")
    if retry.get("reqs_with_exhausted"):
        lines.append(f"- Requirements with exhausted cases: {', '.join(retry['reqs_with_exhausted'])}")
    lines.append("")

    # ── Missing Category Mismatch Summary ──────────────────────────────
    mm: dict = data.get("_category_mismatches", {})
    lines.extend([
        "### Missing Category Mismatch Summary",
        "",
        f"- Requirements with expected categories: **{mm.get('total_requirements_with_expected', 0)}**",
        f"- Exact matches: **{mm.get('total_exact_matches', 0)}**",
        f"- Mismatches: **{mm.get('total_mismatches', 0)}**",
    ])
    mismatches = mm.get("mismatches", [])
    if mismatches:
        lines.extend([
            "",
            "| Requirement | Bucket | Expected | Actual | Missing | Extra |",
            "| --- | --- | --- | --- | --- | --- |",
        ])
        for m in mismatches:
            lines.append(
                f"| {m['requirement_key']} | {m['evaluation_bucket']} | "
                f"{', '.join(m['expected']) or '—'} | "
                f"{', '.join(m['actual']) or '—'} | "
                f"{', '.join(m['missing_from_actual']) or '—'} | "
                f"{', '.join(m['extra_in_actual']) or '—'} |"
            )

        # Bucket-level summary
        bucket_data = mm.get("mismatches_by_bucket", {})
        if bucket_data:
            lines.extend([
                "",
                "**Mismatches by evaluation bucket:**",
                "",
                "| Bucket | Mismatch Count |",
                "| --- | --- |",
            ])
            for bucket, bdata in sorted(bucket_data.items()):
                lines.append(f"| {bucket} | {bdata['count']} |")
    lines.append("")

    # ── Case Count Distribution ────────────────────────────────────────
    case_dist: dict = data.get("_case_distribution", {})
    lines.extend([
        "### Case Count Distribution",
        "",
        f"- Average cases per requirement: **{case_dist.get('average_cases_per_req', 0)}**",
    ])
    dist = case_dist.get("distribution", {})
    if dist:
        lines.extend([
            "",
            "| Case Count | Requirements |",
            "| --- | --- |",
        ])
        for count, reqs in sorted(dist.items()):
            lines.append(f"| {count} | {reqs} |")
    lines.append("")

    high_reqs = case_dist.get("high_count_requirements", [])
    if high_reqs:
        lines.extend([
            f"**Requirements with high case count (>= {case_dist.get('high_threshold', 5)}):**",
            "",
            "| Requirement | Bucket | Case Count |",
            "| --- | --- | --- |",
        ])
        for r in high_reqs:
            lines.append(
                f"| {r['requirement_key']} | {r['evaluation_bucket']} | {r['case_count']} |"
            )
        lines.append("")

    # ── DeepSeek Low Dimension Summary ─────────────────────────────────
    if ds_summary.get("available"):
        lines.extend([
            "### DeepSeek Dimension Summary",
            "",
            f"Overall weighted score: **{ds_summary.get('overall_weighted', 0):.1f}**",
            "",
            "| Dimension | Average |",
            "| --- | --- |",
        ])
        for dim in ALL_DIMENSIONS:
            avg = ds_summary.get("dimension_averages", {}).get(dim, 0)
            label = DIMENSION_LABELS.get(dim, dim)
            flag = " ⚠️" if isinstance(avg, (int, float)) and avg < 3.0 else ""
            lines.append(f"| {label} | **{avg}**{flag} |")

        low_dims = ds_summary.get("low_dimensions", {})
        if low_dims:
            lines.extend([
                "",
                f"**Dimensions below 3.0:** {', '.join(f'{DIMENSION_LABELS.get(d, d)} ({v:.1f})' for d, v in low_dims.items())}",
            ])

        worst = ds_summary.get("worst_requirements", [])
        if worst:
            lines.extend([
                "",
                "**Worst requirements by weighted score:**",
                "",
                "| Requirement | Weighted Score | Coverage Value |",
                "| --- | --- | --- |",
            ])
            for w in worst[:10]:
                lines.append(
                    f"| {w['requirement_key']} | **{w.get('weighted_score', 0):.1f}** | "
                    f"{w.get('coverage_value', 0)} |"
                )

        unscored = ds_summary.get("unscored_requirements", [])
        if unscored:
            lines.extend([
                "",
                f"**Unscored requirements** ({len(unscored)}): {', '.join(unscored[:10])}",
            ])
        lines.append("")
    else:
        lines.extend([
            "### DeepSeek Dimension Summary",
            "",
            "DeepSeek evaluation data not available for this round.",
            "",
        ])


def _render_failure_clusters(data: dict, lines: list[str]) -> None:
    """Render the top failure clusters section."""
    clusters: list = data.get("_clusters", [])
    lines.extend([
        "## Top Failure Clusters",
        "",
    ])

    if not clusters:
        lines.append("No failure clusters detected from available signals.")
        lines.append("")
        return

    # Sort: high severity first
    severity_order = {"high": 0, "medium": 1, "low": 2}
    clusters_sorted = sorted(clusters, key=lambda c: severity_order.get(c.get("severity", "low"), 3))

    for ci, cluster in enumerate(clusters_sorted):
        severity = cluster.get("severity", "low").upper()
        lines.extend([
            f"### {ci + 1}. {cluster['title']}",
            "",
            f"| Property | Value |",
            f"| --- | --- |",
            f"| ID | `{cluster['id']}` |",
            f"| Severity | **{severity}** |",
            f"| Philosophy | {cluster['philosophy_principle']} |",
            f"| Hard-rule items | {', '.join(cluster['related_hardrule_items']) or '—'} |",
            f"| DeepSeek dimensions | {', '.join(cluster['related_deepseek_dimensions']) or '—'} |",
            f"| Affected requirements | {len(cluster.get('affected_requirements', []))} |",
            f"| Affected cases | {cluster.get('affected_case_count', 0)} |",
            "",
        ])

        # Evidence
        lines.extend([
            "**Evidence:**",
            "",
            cluster.get("evidence_summary", ""),
            "",
        ])

        # Affected requirements detail (truncated)
        affected = cluster.get("affected_requirements", [])
        if affected:
            shown = affected[:15]
            suffix = f" ... (+{len(affected) - 15} more)" if len(affected) > 15 else ""
            lines.append(f"**Affected requirements:** {', '.join(shown)}{suffix}")
            lines.append("")

        # Opposite failure risk
        lines.extend([
            "**Opposite failure risk:**",
            "",
            cluster.get("opposite_failure_risk", ""),
            "",
        ])


def _render_philosophy_regressions(data: dict, lines: list[str]) -> None:
    """Render the philosophy regression checks section."""
    regressions = data.get("_regressions", [])
    lines.extend([
        "## Philosophy Regression Checks",
        "",
        "| Check | Status | Evidence |",
        "| --- | --- | --- |",
    ])

    status_icons = {
        "observed": "⚠️ observed",
        "possible": "🔶 possible",
        "not_detected": "✅ not detected",
        "insufficient_data": "❓ insufficient data",
    }

    for r in regressions:
        status = status_icons.get(r["status"], r["status"])
        evidence = r.get("evidence", "") or "—"
        lines.append(f"| {r['check']} | {status} | {evidence} |")

    lines.append("")


def _render_representative_cases(data: dict, lines: list[str]) -> None:
    """Render the representative cases section."""
    rep_cases = data.get("_representative_cases", [])

    lines.extend([
        "## Representative Cases",
        "",
        "Cases a human should inspect before changing prompts.",
        "",
    ])

    if not rep_cases:
        lines.append("No representative cases selected.")
        lines.append("")
        return

    for i, rc in enumerate(rep_cases):
        lines.extend([
            f"### Rep Case {i + 1}: {rc['case_title'][:80]}",
            "",
            f"| Property | Value |",
            f"| --- | --- |",
            f"| Requirement | `{rc['requirement_key']}` |",
            f"| Bucket | {rc['evaluation_bucket'] or '—'} |",
            f"| Case index | {rc['case_index']} |",
            f"| Selection reason | {rc['selection_reason']} |",
            f"| Related clusters | {', '.join(rc['cluster_ids']) if rc['cluster_ids'] else '—'} |",
            f"| Retry attempts | {rc['retry_attempts']} |",
            f"| Retry exhausted | {'Yes' if rc['retry_exhausted'] else 'No'} |",
        ])

        failures = rc.get("hardrule_failures", [])
        if failures:
            lines.append(f"| Hard-rule failures | {', '.join(failures)} ({len(failures)} items) |")
        else:
            lines.append("| Hard-rule failures | None |")

        ds_notes = rc.get("deepseek_notes", [])
        if ds_notes:
            lines.append("")
            lines.append("**DeepSeek notes:**")
            for note in ds_notes:
                lines.append(f"- {note}")

        lines.append("")


def _render_root_cause_hypotheses(data: dict, lines: list[str]) -> None:
    """Render the prompt root-cause hypotheses section (placeholder for v1)."""
    clusters: list = data.get("_clusters", [])

    lines.extend([
        "## Prompt Root-Cause Hypotheses",
        "",
        "Deterministic v1 does not infer final prompt root causes. "
        "Use the failure clusters and representative cases above for human review.",
        "",
        "| ID | Related Cluster | Suspected Prompt Area | Evidence | Opposite Failure Risk | Confidence |",
        "| --- | --- | --- | --- | --- | --- |",
    ])

    # Map clusters to obvious suspected prompt areas
    cluster_prompt_map = {
        "missing_info_false_negative": {
            "area": "generate_case.system — Missing Information / [NEEDS REVIEW] rules",
            "evidence": "See failure cluster evidence above.",
            "opposite": "Over-marking → 3.2.3 false positives",
        },
        "missing_info_false_positive": {
            "area": "generate_case.system — [NEEDS REVIEW] usage rules / anti-over-marking clause",
            "evidence": "See failure cluster evidence above.",
            "opposite": "Under-marking → 3.2.1 false negatives",
        },
        "action_judgment_mixing": {
            "area": "generate_case.system — Action/Expected boundary rules",
            "evidence": "See failure cluster evidence above.",
            "opposite": "Mechanical splitting without improving test value",
        },
        "wait_action_not_separated": {
            "area": "generate_case.system — Step structure / timing placeholder rules",
            "evidence": "See failure cluster evidence above.",
            "opposite": "Verbose case structures",
        },
        "case_count_inflation": {
            "area": "generate_case.system — Case splitting philosophy / coverage rules",
            "evidence": "See failure cluster evidence above.",
            "opposite": "Suppressing legitimate boundary or diagnostic cases",
        },
        "low_executability": {
            "area": "generate_case.system — Executability / concrete step rules",
            "evidence": "See failure cluster evidence above.",
            "opposite": "Pseudo-specific details not in test basis",
        },
        "low_automation_readiness": {
            "area": "generate_case.system — Automation readiness / structure rules",
            "evidence": "See failure cluster evidence above.",
            "opposite": "Sacrificing natural-language clarity for automation form",
        },
    }

    for i, cluster in enumerate(clusters):
        cid = cluster["id"]
        mapping = cluster_prompt_map.get(cid, {
            "area": "Unknown",
            "evidence": "See failure cluster evidence.",
            "opposite": "Unknown",
        })
        lines.append(
            f"| H{i + 1} | {cid} | {mapping['area']} | "
            f"{mapping['evidence']} | {mapping['opposite']} | low |"
        )

    if not clusters:
        lines.append("| — | — | — | — | — | — |")

    lines.append("")


def _render_patch_candidates(data: dict, lines: list[str]) -> None:
    """Render the patch candidates section (placeholder for v1)."""
    lines.extend([
        "## Patch Candidates",
        "",
        "No patch is automatically recommended in deterministic v1. "
        "Use the checklist below before accepting any manual patch.",
        "",
        "| ID | Target Cluster | Protected Principle | Representative Target Cases | "
        "Representative Opposite Cases | Human Decision |",
        "| --- | --- | --- | --- | --- | --- |",
        "| — | — | — | — | — | — |",
        "",
    ])


def _render_human_review_checklist(data: dict, lines: list[str]) -> None:
    """Render the human review checklist."""
    lines.extend([
        "## Human Review Checklist",
        "",
        "Before accepting any prompt patch, confirm:",
        "",
        "- [ ] Is the target failure real?",
        "- [ ] Does the proposed change preserve `case-generation-philosophy.md`?",
        "- [ ] Does the change avoid benchmark-specific wording?",
        "- [ ] Did we inspect at least one target-failure case?",
        "- [ ] Did we inspect at least one opposite-failure risk case?",
        "- [ ] Could this patch increase `[NEEDS REVIEW]` misuse?",
        "- [ ] Could this patch increase case count inflation?",
        "- [ ] Could this patch reduce executability or automation readiness?",
        "- [ ] Is the patch small enough to evaluate in the next run?",
        "",
    ])


# ── CLI ────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a deterministic prompt debug report from an evaluation round."
    )
    parser.add_argument(
        "--round-dir", required=True,
        help="Path to the round directory containing summary.json, generated_cases.json, etc.",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output path for the report. Defaults to <round-dir>/prompt_debug_report.md",
    )
    args = parser.parse_args()

    round_dir = Path(args.round_dir)
    if not round_dir.is_absolute():
        round_dir = round_dir.resolve()

    if not round_dir.is_dir():
        print(f"Error: round directory not found: {round_dir}")
        return

    data = load_round(round_dir)
    report = generate_report(data)

    output_path = Path(args.output) if args.output else round_dir / "prompt_debug_report.md"
    output_path.write_text(report, encoding="utf-8")
    print(f"Prompt debug report saved to: {output_path}")


if __name__ == "__main__":
    main()
