"""Evaluation engine for generated test cases.

This module owns checklist rules and aggregate evaluation results. Report
renderers should consume its output rather than re-implementing rule logic.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


CHECKLIST = {
    "1.1.1": ("title 不为空/非placeholder", "结构完整性"),
    "1.1.2": ("objective 不为空", "结构完整性"),
    "1.1.3": ("precondition 不为空", "结构完整性"),
    "1.1.4": ("postcondition 不为空", "结构完整性"),
    "1.1.5": ("至少1个step且有action", "结构完整性"),
    "1.1.6": ("related_requirement 存在", "结构完整性"),
    "2.1.1": ("已知信号名在case中引用", "领域正确性"),
    "2.1.2": ("不凭空发明标识符", "领域正确性"),
    "2.2.1": ("不凭空发明数值阈值", "领域正确性"),
    "2.2.2": ("符号化参数名视为有效值", "领域正确性"),
    "3.2.1": ("[HARD] 需要signal/threshold/timing/state/observation但case未标[NEEDS REVIEW]", "NEEDS REVIEW规范"),
    "3.2.2": ("[HARD] action/expected编造需求未提供的signal/threshold/timing/state/observation", "NEEDS REVIEW规范"),
    "3.2.3": ("[WARNING] 需求语义完整但case添加不必要[NEEDS REVIEW]", "NEEDS REVIEW规范"),
    "3.3.1": ("[NEEDS REVIEW]只能放在action/expected，不放在title/objective/precondition/postcondition", "NEEDS REVIEW规范"),
    "3.3.2": ("timing缺失时[NEEDS REVIEW]应放在Wait action", "NEEDS REVIEW规范"),
    "3.3.3": ("禁止[NEEDS REVIEW: timing]带category后缀", "NEEDS REVIEW规范"),
    "4.1.1": ("时序等待与执行动作分两步 [WARNING]", "步骤质量"),
    "4.1.4": ("action 不包含意图叙述（无 such that / in order to 等）", "步骤质量"),
    "4.1.5": ("action 不冗长（每条 ≤15 词）", "步骤质量"),
    "4.2.1": ("至少一个expected具体可观测", "步骤质量"),
    "4.2.2": ("无模糊expected result", "步骤质量"),
    "4.2.3": ("无read/check-only expected", "步骤质量"),
    "4.2.4": ("expected 不冗长（每条 ≤15 词）", "步骤质量"),
    "5.2.1": ("触发/不触发等价类覆盖", "覆盖维度"),
    "5.2.2": ("边界值case覆盖", "覆盖维度"),
    "5.2.3": ("参数/时序正交拆分", "覆盖维度"),
    "6.1.1": ("所有case统一precondition", "测试工程深度"),
    "6.1.2": ("所有case统一postcondition", "测试工程深度"),
    "6.1.3": ("setup动作放action非precondition", "测试工程深度"),
    "6.2.1": ("Title描述测试条件和预期行为", "测试工程深度"),
    "6.3.1": ("每个case仅验证一个需求的一个行为", "测试工程深度"),
    "6.3.2": ("不合并多个阈值场景", "测试工程深度"),
}


@dataclass
class CaseEvaluation:
    requirement_key: str
    case_index: int
    case_title: str
    failed_items: list[str] = field(default_factory=list)
    warning_items: list[str] = field(default_factory=list)


@dataclass
class EvaluationResult:
    total_cases: int = 0
    total_passed: int = 0
    case_pass_rate: float = 0.0
    case_results: dict[tuple[str, int], CaseEvaluation] = field(default_factory=dict)
    item_fail_counts: Counter[str] = field(default_factory=Counter)
    item_warning_counts: Counter[str] = field(default_factory=Counter)
    hard_gate_records: list[dict[str, Any]] = field(default_factory=list)
    manual_review_summary: dict[str, Any] = field(default_factory=dict)


def evaluate_generated_cases(
    data: list[dict[str, Any]],
    manual_review_entries: list[Any] | None = None,
) -> EvaluationResult:
    """Evaluate generated_cases.json data and return aggregate results."""
    result = EvaluationResult()

    for req in data:
        base_info = _enrich_req_info(req)
        req_key = req["requirement_key"]

        for case_index, case in enumerate(req.get("cases", [])):
            coverage = ""
            intents = req.get("analysis", {}).get("case_intents", [])
            if case_index < len(intents):
                coverage = intents[case_index].get("coverage", "")

            req_info = dict(base_info)
            req_info["case_coverage"] = coverage
            failed, warnings = evaluate_case(case, req_info, {})

            result.total_cases += 1
            if not failed:
                result.total_passed += 1
            for item in failed:
                result.item_fail_counts[item] += 1
            for item in warnings:
                result.item_warning_counts[item] += 1

            result.case_results[(req_key, case_index)] = CaseEvaluation(
                requirement_key=req_key,
                case_index=case_index,
                case_title=case.get("title", ""),
                failed_items=failed,
                warning_items=warnings,
            )

    result.case_pass_rate = (
        round(result.total_passed / result.total_cases * 100, 1)
        if result.total_cases
        else 0.0
    )
    result.hard_gate_records = evaluate_missing_info_hard_gates(data)

    if manual_review_entries is not None:
        from optimization.manual_review import get_review_summary

        result.manual_review_summary = get_review_summary(manual_review_entries, data)

    return result


def evaluate_manual_review_hard_gates(
    entry: Any,
    generated_case: dict | None = None,
    expected_missing_categories: list[str] | None = None,
) -> dict[str, Any]:
    """Evaluate manual-review hard gates using the shared case evaluator."""
    result: dict[str, Any] = {
        "unacceptable": False,
        "reasons": [],
        "warnings": [],
    }

    information_integrity = getattr(entry, "information_integrity", 0)
    if information_integrity < 3:
        result["unacceptable"] = True
        result["reasons"].append(
            f"information_integrity={information_integrity} (< 3)"
        )

    if generated_case is None:
        return result

    normalized_case = _normalize_case_for_manual_gate(entry, generated_case)
    req_info = {
        "signals": [],
        "thresholds": [],
        "timing": [],
        "case_coverage": "",
        "requirement_description": "",
        "supplementary_info": "",
        "expected_missing_categories": expected_missing_categories or [],
    }
    failed, warnings = evaluate_case(normalized_case, req_info, {})

    if "3.2.1" in failed:
        result["unacceptable"] = True
        result["reasons"].append(
            f"Expected missing {expected_missing_categories} but case lacks [NEEDS REVIEW]"
        )
    if "3.2.2" in failed:
        result["unacceptable"] = True
        result["reasons"].append(
            "Case contains numeric value(s) that appear to invent "
            "missing threshold/timing semantics"
        )
    if "3.2.3" in warnings:
        result["warnings"].append(
            "Requirement appears semantically complete but case contains "
            "[NEEDS REVIEW] — penalized but not automatically severe"
        )

    return result


def _normalize_case_for_manual_gate(entry: Any, generated_case: dict) -> dict:
    return {
        "title": generated_case.get("title", ""),
        "objective": generated_case.get("objective", ""),
        "precondition": generated_case.get("precondition", ""),
        "postcondition": generated_case.get("postcondition", ""),
        "related_requirement": generated_case.get("related_requirement", entry.requirement_key),
        "steps": generated_case.get("steps", []),
        "raw_html": generated_case.get("raw_html", ""),
    }


def evaluate_case(case: dict, req_info: dict, global_data: dict) -> tuple[list[str], list[str]]:
    """Evaluate a single case against checklist items.

    Returns (failed_item_ids, warning_item_ids).
    """
    failed: list[str] = []
    warnings: list[str] = []

    title = case["title"].strip()
    obj = case["objective"].strip()
    pre = case["precondition"].strip()
    post = case["postcondition"].strip()
    steps = case["steps"]

    signals = [s.strip() for s in req_info.get("signals", []) if s.strip()]
    thresholds = [t.strip() for t in req_info.get("thresholds", []) if t.strip()]
    timing = [t.strip() for t in req_info.get("timing", []) if t.strip() and t.strip().lower() != "none found"]
    expected_missing = req_info.get("expected_missing_categories", [])

    all_expected = " ".join([s["expected"] or "" for s in steps]).lower()
    rr = case.get("related_requirement", "").strip()

    steps_lower = "".join(
        s["action"] + (s.get("expected") or "")
        for s in steps
    ).lower()
    non_step_fields = f"{title} {obj} {pre} {post}".lower()
    has_needs_review = "[needs review]" in f"{non_step_fields} {steps_lower}"

    if not title or title.lower() in {"draft test case", "test case", "boundary test"}:
        failed.append("1.1.1")
    if not obj:
        failed.append("1.1.2")
    if not pre:
        failed.append("1.1.3")
    if not post:
        failed.append("1.1.4")
    if not steps:
        failed.append("1.1.5")
    if not rr:
        failed.append("1.1.6")

    if signals and all_expected:
        if not any(s.lower() in all_expected for s in signals):
            failed.append("2.1.1")

    req_desc = req_info.get("requirement_description", "").lower()
    supp_info = req_info.get("supplementary_info", "").lower()
    known_text = req_desc + " " + supp_info + " " + " ".join(timing + thresholds + signals).lower()
    for step in steps:
        text = f"{step['action']} {step['expected'] or ''}"
        found_nums = re.findall(r"\d+\.?\d*\s*(?:deg\s*C|°C|kOhm|MOhm|mOhm|kΩ|MΩ|mΩ|mV|mA|ms|ohm|Ω|deg|V|A|s|%)(?!\w)", text, re.IGNORECASE)
        for num in found_nums:
            if num.lower() not in known_text:
                failed.append("2.2.1")
                break
        else:
            continue
        break

    if expected_missing:
        nr_in_steps = any(
            "[needs review]" in (s["action"] + str(s["expected"] or "")).lower()
            for s in steps
        )
        if not nr_in_steps:
            failed.append("3.2.1")

    if expected_missing:
        if "threshold" in expected_missing:
            for step in steps:
                text = f"{step['action']} {step['expected'] or ''}"
                if re.search(r"\d+\.?\d+", text) and "[needs review]" not in text.lower():
                    failed.append("3.2.2")
                    break

    if has_needs_review and not expected_missing:
        warnings.append("3.2.3")

    nr_in_non_step = "[needs review]" in non_step_fields
    if nr_in_non_step:
        failed.append("3.3.1")

    needs_review_in_steps = any(
        "[needs review]" in (s["action"] + str(s["expected"] or "")).lower()
        for s in steps
    )
    if "timing" in expected_missing and needs_review_in_steps:
        nr_in_wait = any(
            "[needs review]" in s["action"].lower() and "wait" in s["action"].lower()
            for s in steps
        )
        if not nr_in_wait:
            failed.append("3.3.2")

    nr_with_suffix_pattern = re.compile(
        r"\[needs review\s*:\s*\w+\]", re.IGNORECASE
    )
    if nr_with_suffix_pattern.search(case.get("raw_html", "")) or nr_with_suffix_pattern.search(steps_lower):
        failed.append("3.3.3")

    has_merged_wait = False
    wait_count = 0
    separated_count = 0
    for i, step in enumerate(steps):
        action = step["action"].strip().lower()
        expected = step["expected"]
        if "wait" in action:
            wait_count += 1
            if expected and expected != "none":
                has_merged_wait = True
            if i + 1 < len(steps):
                next_expected = (steps[i + 1]["expected"] or "").strip()
                if next_expected and next_expected.lower() != "none":
                    separated_count += 1
    if has_merged_wait and separated_count < wait_count:
        warnings.append("4.1.1")

    intent_patterns = ["such that", "in order to", "to verify", "to ensure",
                       "to check", "so that", "to confirm", "to validate"]
    for step in steps:
        action = step["action"].strip().lower()
        if any(pattern in action for pattern in intent_patterns):
            failed.append("4.1.4")
            break

    for step in steps:
        action = step["action"].strip()
        if not action:
            continue
        if len(action.split()) > 15:
            failed.append("4.1.5")
            break

    has_concrete = any(
        (s["expected"] or "").strip().lower() not in ("", "none", "null") and len((s["expected"] or "").strip()) > 10
        for s in steps
    )
    if not has_concrete:
        failed.append("4.2.1")

    for step in steps:
        expected = (step["expected"] or "").lower()
        if expected and any(v in expected for v in ["system works correctly", "behaves as expected", "works as expected"]):
            failed.append("4.2.2")
            break

    for step in steps:
        expected = (step["expected"] or "").lower()
        action = step["action"].lower()
        if expected and any(v in expected for v in ["read", "check", "verify", "observe", "monitor", "capture"]):
            if not any(w in action for w in ["set", "apply", "simulate"]):
                if len(expected.split()) < 8:
                    failed.append("4.2.3")
                    break

    for step in steps:
        expected = (step["expected"] or "").strip()
        if not expected or expected.lower() == "none":
            continue
        if len(expected.split()) > 15:
            failed.append("4.2.4")
            break

    pre_keywords = ["bms initialized", "normal operating", "no active fault"]
    pre_lower = pre.lower()
    if not any(kw in pre_lower for kw in pre_keywords):
        failed.append("6.1.1")

    post_lower = post.lower()
    if not ("return" in post_lower or "normal" in post_lower or "restored" in post_lower):
        failed.append("6.1.2")

    for step in steps:
        action = step["action"].strip().lower()
        if any(p in action for p in ["bms shall", "bms initiates", "bms verifies",
                                     "bms injects", "bms should", "bms performs"]):
            failed.append("6.1.3")
            break

    if title.lower() in {"draft test case", "test case", "boundary test"}:
        failed.append("6.2.1")

    return failed, warnings


def _enrich_req_info(req: dict) -> dict:
    """Build the req_info dict needed by evaluate_case from a requirement entry."""
    signals = req["analysis"]["signals"]
    thresholds = req["analysis"].get("thresholds", [])
    timing = [t for t in req["analysis"].get("timing", []) if t.strip().lower() != "none found"]

    info: dict = {
        "signals": signals,
        "thresholds": thresholds,
        "timing": timing,
        "case_coverage": "",
        "requirement_description": req.get("description", ""),
        "supplementary_info": req.get("supplementary_info", ""),
    }
    if req.get("expected_missing_categories") is not None:
        info["expected_missing_categories"] = req["expected_missing_categories"]
    if req.get("evaluation_bucket"):
        info["evaluation_bucket"] = req["evaluation_bucket"]
    actual = req.get("analysis", {}).get("missing_info_items", [])
    if actual:
        info["actual_missing_categories"] = [mi["category"] for mi in actual if mi.get("category")]
    return info


def evaluate_missing_info_hard_gates(data: list[dict]) -> list[dict]:
    """Compare expected vs actual missing categories per requirement."""
    records: list[dict] = []
    for req in data:
        expected = req.get("expected_missing_categories")
        if not expected:
            continue
        actual_items = req.get("analysis", {}).get("missing_info_items", [])
        actual_cats = {mi["category"] for mi in actual_items if mi.get("category")}

        missing_cats = [c for c in expected if c not in actual_cats]
        extra_cats = [c for c in actual_cats if c not in expected]
        matched = [c for c in expected if c in actual_cats]

        item_ids: list[str] = []
        if missing_cats:
            item_ids.append("3.2.1")
        if extra_cats:
            item_ids.append("3.2.3")

        case_issues: list[dict] = []
        for case in req.get("cases", []):
            nr_in_steps = any(
                "[needs review]" in (s["action"] + str(s["expected"] or "")).lower()
                for s in case.get("steps", [])
            )
            if expected and not nr_in_steps:
                case_issues.append({
                    "case_title": case.get("title", ""),
                    "issue": "missing [NEEDS REVIEW] in action/expected",
                    "missing_categories": expected,
                    "item_id": "3.2.1",
                })

        records.append({
            "requirement_key": req["requirement_key"],
            "evaluation_bucket": req.get("evaluation_bucket", ""),
            "expected_missing_categories": expected,
            "actual_missing_categories": sorted(actual_cats),
            "matched": matched,
            "missing_from_actual": missing_cats,
            "extra_in_actual": extra_cats,
            "case_issues": case_issues,
            "item_ids": item_ids,
        })
    return records


# ── Shared evaluation persistence ──────────────────────────────────────


def save_evaluation_result(
    result: EvaluationResult,
    evaluator_name: str,
    round_dir: "Path",
) -> "Path":
    """Save an EvaluationResult to {evaluator_name}_evaluation.json.

    Args:
        result: Aggregated EvaluationResult from evaluate_generated_cases().
        evaluator_name: e.g. 'hardrule', 'deepseek'.
        round_dir: Round directory to save into.
    """
    from pathlib import Path as _Path  # noqa: F811

    # Build per-case items from result.case_results
    cases: list[dict[str, object]] = []
    for (req_key, ci), ce in result.case_results.items():
        items: list[dict[str, str]] = []
        for item_id in ce.failed_items:
            items.append({"item_id": item_id, "result": "fail", "note": ""})
        for item_id in ce.warning_items:
            items.append({"item_id": item_id, "result": "warning", "note": ""})
        # Mark passed items: all CHECKLIST items not in failed or warning
        passed_ids = [
            iid for iid in CHECKLIST
            if iid not in ce.failed_items and iid not in ce.warning_items
        ]
        for item_id in passed_ids:
            items.append({"item_id": item_id, "result": "pass", "note": ""})

        cases.append({
            "requirement_key": req_key,
            "case_index": ci,
            "case_title": ce.case_title,
            "items": items,
        })

    output: dict[str, object] = {
        "checklist_version": "checklist_v2.md",
        "evaluated_by": evaluator_name,
        "total_cases": result.total_cases,
        "total_passed": result.total_passed,
        "case_pass_rate": result.case_pass_rate,
        "errors": 0,
        "item_pass_counts": {
            iid: result.total_cases - result.item_fail_counts.get(iid, 0)
            - result.item_warning_counts.get(iid, 0)
            for iid in CHECKLIST
        },
        "item_fail_counts": dict(result.item_fail_counts),
        "item_warning_counts": dict(result.item_warning_counts),
        "item_skip_counts": {},
        "cases": cases,
        "cross_case": [],
    }

    save_path = _Path(round_dir) / f"{evaluator_name}_evaluation.json"
    save_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return save_path


def load_evaluation(round_dir: "Path", evaluator_name: str) -> dict[str, object] | None:
    """Load evaluation results from {evaluator_name}_evaluation.json if it exists."""
    from pathlib import Path as _Path  # noqa: F811

    path = _Path(round_dir) / f"{evaluator_name}_evaluation.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def load_all_evaluations(round_dir: "Path") -> dict[str, dict[str, object]]:
    """Load all available evaluation results from a round directory."""
    results: dict[str, dict[str, object]] = {}
    for name in ["hardrule", "deepseek"]:
        data = load_evaluation(round_dir, name)
        if data is not None:
            results[name] = data
    return results
