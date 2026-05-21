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
    "1.1.5": ("至少1个step且有action，且至少一个step有非空expected", "结构完整性"),
    "1.1.6": ("related_requirement 字段存在且非空", "结构完整性"),
    "2.1.1": ("已知信号名在case中引用（匹配时忽略标点）", "领域正确性"),
    "2.1.2": ("不凭空发明当前需求或accepted test basis未提供的标识符", "领域正确性"),
    "2.2.1": ("不凭空发明当前需求或accepted test basis未提供的数值阈值", "领域正确性"),
    "2.2.2": ("符号化参数名视为有效值（可用于Set或Wait步骤）", "领域正确性"),
    "3.2.1": ("[HARD] 需signal/threshold/timing/state/observation但当前需求未提供且case未标[NEEDS REVIEW]", "NEEDS REVIEW规范"),
    "3.2.2": ("[HARD] action/expected编造当前需求或accepted test basis未提供的signal/threshold/timing/state/observation", "NEEDS REVIEW规范"),
    "3.2.3": ("[HARD] 需求语义完整但case添加不必要[NEEDS REVIEW]", "NEEDS REVIEW规范"),
    "3.3.1": ("[NEEDS REVIEW]只能放在action/expected，不放在title/objective/precondition/postcondition", "NEEDS REVIEW规范"),
    "3.3.2": ("timing缺失时[NEEDS REVIEW]需单独一条Wait step", "NEEDS REVIEW规范"),
    "3.3.3": ("[WARNING] [NEEDS REVIEW]不推荐带category后缀", "NEEDS REVIEW规范"),
    "4.1.1": ("输入刺激建立与BMS响应等待/验证分离", "步骤质量"),
    "4.1.4": ("action不含意图叙述和观察动词（such that/in order to/check/verify等）", "步骤质量"),
    "4.2.2": ("无模糊expected result", "步骤质量"),
    "4.2.3": ("expected不只有read/check/verify等观察动词或空[NEEDS REVIEW]而无期望值", "步骤质量"),
    "5.1.1": ("normal_behavior的case描述正常功能路径的触发和响应，且不违反阈值/时序边界语义", "覆盖维度"),
    "5.1.2": ("boundary_or_threshold的case测试阈值边界的触发/不触发行为", "覆盖维度"),
    "5.1.3": ("fault_or_protection的case测试故障场景和保护响应", "覆盖维度"),
    "5.1.4": ("state_transition的case测试状态变更", "覆盖维度"),
    "5.1.5": ("observability的case验证信号/数据可观测性", "覆盖维度"),
    "5.2.1": ("触发/不触发等价类覆盖 [LLM evaluator]", "覆盖维度"),
    "5.2.2": ("边界值case覆盖 [LLM evaluator]", "覆盖维度"),
    "5.2.3": ("参数/时序正交拆分 [LLM evaluator]", "覆盖维度"),
    "6.1.1": ("所有case统一precondition [LLM evaluator]", "测试工程深度"),
    "6.1.2": ("所有case统一postcondition [LLM evaluator]", "测试工程深度"),
    "6.1.3": ("setup动作放action非precondition", "测试工程深度"),
    "6.2.1": ("Title描述测试条件和预期行为", "测试工程深度"),
    "6.3.1": ("每个case仅验证一个需求的一个行为", "测试工程深度"),
    "6.3.2": ("不合并多个阈值场景", "测试工程深度"),
}


_CODE_IDENTIFIER_RE = re.compile(r"\b(?:BMS|CAN|DTC)_[A-Za-z0-9_]+\b", re.IGNORECASE)
_NEEDS_REVIEW_RE = re.compile(r"\[needs review\]", re.IGNORECASE)
_REQ_ASSIGN_ONE_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_]*)\b\s*(?::=|==|=)\s*1\b",
    re.IGNORECASE,
)
_BOUNDARY_VALUE_PATTERN = (
    r"[A-Za-z_][A-Za-z0-9_]*|"
    r"\d+(?:\.\d+)?\s*(?:deg\s*C|°C|mV|mA|ms|V|A|s|%)?"
)
_INCLUSIVE_RELATION_PATTERNS = [
    re.compile(rf"(?:>=|=>|≥)\s*(?P<value>{_BOUNDARY_VALUE_PATTERN})", re.IGNORECASE),
    re.compile(rf"(?:<=|=<|≤)\s*(?P<value>{_BOUNDARY_VALUE_PATTERN})", re.IGNORECASE),
    re.compile(
        rf"\b(?:at\s+or\s+above|at\s+least|no\s+less\s+than|not\s+less\s+than|"
        rf"reach(?:es|ed)?)\s+(?P<value>{_BOUNDARY_VALUE_PATTERN})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:at\s+or\s+below|at\s+most|no\s+more\s+than|not\s+greater\s+than|"
        rf"not\s+higher\s+than)\s+(?P<value>{_BOUNDARY_VALUE_PATTERN})",
        re.IGNORECASE,
    ),
    re.compile(rf"(?:达到|不低于|不小于|不高于|不大于)\s*(?P<value>{_BOUNDARY_VALUE_PATTERN})", re.IGNORECASE),
]
_STRICT_RELATION_PATTERNS = [
    re.compile(rf"(?:>|＞)\s*(?P<value>{_BOUNDARY_VALUE_PATTERN})", re.IGNORECASE),
    re.compile(rf"(?:<|＜)\s*(?P<value>{_BOUNDARY_VALUE_PATTERN})", re.IGNORECASE),
    re.compile(
        rf"\b(?:above|greater\s+than|exceeds?|higher\s+than|more\s+than)\s+"
        rf"(?P<value>{_BOUNDARY_VALUE_PATTERN})",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?:below|less\s+than|lower\s+than|shorter\s+than|before)\s+"
        rf"(?P<value>{_BOUNDARY_VALUE_PATTERN})",
        re.IGNORECASE,
    ),
    re.compile(rf"(?:高于|超过|大于|低于|小于|短于|未达到)\s*(?P<value>{_BOUNDARY_VALUE_PATTERN})", re.IGNORECASE),
]
_WITHIN_TIME_RE = re.compile(
    rf"\bwithin\s+(?P<value>{_BOUNDARY_VALUE_PATTERN})|"
    rf"(?P<cn_value>{_BOUNDARY_VALUE_PATTERN})\s*(?:内|以内|之内)",
    re.IGNORECASE,
)
_SET_ACTION_RE = re.compile(
    r"^\s*(?:set|change|adjust|apply|inject|force|simulate|command|drive)\b",
    re.IGNORECASE,
)
_UNIT_PATTERN = r"deg\s*C|°C|kOhm|MOhm|mOhm|kΩ|MΩ|mΩ|mV|mA|ms|ohm|Ω|deg|V|A|s|%"
_NUMERIC_VALUE_RE = re.compile(
    rf"\d+\.?\d*\s*(?P<unit>{_UNIT_PATTERN})(?!\w)",
    re.IGNORECASE,
)


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
    if "3.2.3" in failed:
        result["unacceptable"] = True
        result["reasons"].append(
            "Requirement appears semantically complete but case contains "
            "unnecessary [NEEDS REVIEW]"
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


def _normalize_token(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _only_needs_review(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return not _NEEDS_REVIEW_RE.sub("", stripped).strip(" .:;,-_/")


def _unsupported_identifiers(
    step_text: str,
    requirement_text: str,
    accepted_test_basis: str = "",
) -> list[str]:
    supported_text = f"{requirement_text} {accepted_test_basis}"
    supported = {m.group(0).lower() for m in _CODE_IDENTIFIER_RE.finditer(supported_text)}
    used = {m.group(0) for m in _CODE_IDENTIFIER_RE.finditer(step_text)}
    return sorted(ident for ident in used if ident.lower() not in supported)


def _normalized_unit(unit: str) -> str:
    return unit.lower().replace(" ", "")


def _is_supported_numeric_value(value_text: str, known_text: str) -> bool:
    if value_text.lower() in known_text:
        return True

    match = _NUMERIC_VALUE_RE.fullmatch(value_text.strip())
    if not match:
        return False

    num_match = re.match(r"\d+\.?\d*", value_text.strip())
    if not num_match:
        return False

    value = float(num_match.group(0))
    unit = _normalized_unit(match.group("unit"))

    for known_match in _NUMERIC_VALUE_RE.finditer(known_text):
        known_num_match = re.match(r"\d+\.?\d*", known_match.group(0))
        if not known_num_match:
            continue
        known_value = float(known_num_match.group(0))
        known_unit = _normalized_unit(known_match.group("unit"))
        if unit == known_unit and known_value > 0:
            if abs(value - known_value) / known_value <= 0.20:
                return True

    return False


def _has_negative_expectation_for_signal(expected_text: str, signal: str) -> bool:
    sig = re.escape(signal)
    patterns = [
        rf"\b{sig}\b\s*(?:==|:=|=)\s*0\b",
        rf"\b{sig}\b[^&.;\n]*(?:not\s+set|remains?\s+unset|inactive|not\s+active)",
    ]
    return any(re.search(pattern, expected_text, re.IGNORECASE) for pattern in patterns)


def _has_positive_expectation_for_signal(expected_text: str, signal: str) -> bool:
    sig = re.escape(signal)
    patterns = [
        rf"\b{sig}\b\s*(?:==|:=|=)\s*1\b",
        rf"\b{sig}\b[^&.;\n]*(?:set|active|becomes?\s+active|asserted)",
    ]
    return any(re.search(pattern, expected_text, re.IGNORECASE) for pattern in patterns)


def _value_regex(value: str) -> str:
    return re.escape(value.strip()).replace(r"\ ", r"\s*")


def _extract_trigger_boundaries(requirement_text: str) -> list[tuple[str, bool]]:
    boundaries: list[tuple[str, bool]] = []
    for pattern in _INCLUSIVE_RELATION_PATTERNS:
        for match in pattern.finditer(requirement_text):
            value = match.groupdict().get("value")
            if value:
                boundaries.append((value.strip(), True))
    for pattern in _STRICT_RELATION_PATTERNS:
        for match in pattern.finditer(requirement_text):
            value = match.groupdict().get("value")
            if value:
                boundaries.append((value.strip(), False))
    return boundaries


def _action_sets_exact_boundary(action_text: str, boundary_value: str) -> bool:
    if not action_text.strip() or not boundary_value.strip():
        return False
    value = _value_regex(boundary_value)
    action_lower = action_text.lower()
    if _normalize_token(boundary_value) not in _normalize_token(action_text):
        return False

    relation_before_value = [
        "above", "greater than", "exceeds", "exceed", "higher than", "more than",
        "below", "less than", "lower than", "shorter than", "before",
        "at least", "at most", "no less than", "no more than",
    ]
    for relation in relation_before_value:
        if re.search(rf"\b{re.escape(relation)}\s+(?:the\s+)?{value}\b", action_lower, re.IGNORECASE):
            return False
    if re.search(rf"(?:>=|<=|>|<|≥|≤|＞|＜)\s*(?:the\s+)?{value}\b", action_text, re.IGNORECASE):
        return False

    exact_patterns = [
        rf"\b(?:to|at|exactly|equals?|for|wait(?:\s+for)?|reach(?:es|ed)?)\s+(?:the\s+)?{value}\b",
        rf"(?:==|=)\s*(?:the\s+)?{value}\b",
    ]
    return any(re.search(pattern, action_text, re.IGNORECASE) for pattern in exact_patterns)


def _contradicts_trigger_boundary(steps: list[dict], requirement_text: str) -> bool:
    action_text = " ".join(step.get("action", "") for step in steps)
    expected_text = " ".join(str(step.get("expected") or "") for step in steps)
    assigned_signals = {
        match.group(1)
        for match in _REQ_ASSIGN_ONE_RE.finditer(requirement_text)
    }
    if not assigned_signals:
        return False

    for boundary_value, inclusive in _extract_trigger_boundaries(requirement_text):
        if not _action_sets_exact_boundary(action_text, boundary_value):
            continue
        for signal in assigned_signals:
            if inclusive and _has_negative_expectation_for_signal(expected_text, signal):
                return True
            if not inclusive and _has_positive_expectation_for_signal(expected_text, signal):
                return True
    return False


def _action_waits_before_time_bound(action_text: str, bound_value: str) -> bool:
    if _normalize_token(bound_value) not in _normalize_token(action_text):
        return False
    value = _value_regex(bound_value)
    before_patterns = [
        rf"\b(?:shorter\s+than|less\s+than|before|prior\s+to|under)\s+(?:the\s+)?{value}\b",
        rf"(?:<|＜)\s*(?:the\s+)?{value}\b",
        rf"(?:短于|少于|小于|未达到)\s*(?:the\s+)?{value}\b",
        rf"{value}\s*(?:前|之前)",
    ]
    return any(re.search(pattern, action_text, re.IGNORECASE) for pattern in before_patterns)


def _contradicts_response_time_bound(steps: list[dict], requirement_text: str) -> bool:
    expected_text = " ".join(str(step.get("expected") or "") for step in steps)
    assigned_signals = {
        match.group(1)
        for match in _REQ_ASSIGN_ONE_RE.finditer(requirement_text)
    }
    if not assigned_signals:
        return False

    response_bounds = []
    for match in _WITHIN_TIME_RE.finditer(requirement_text):
        value = match.groupdict().get("value") or match.groupdict().get("cn_value")
        if value:
            response_bounds.append(value.strip())
    if not response_bounds:
        return False

    action_text = " ".join(step.get("action", "") for step in steps)
    waits_before_bound = any(
        _action_waits_before_time_bound(action_text, bound)
        for bound in response_bounds
    )
    if not waits_before_bound:
        return False

    return any(
        _has_negative_expectation_for_signal(expected_text, signal)
        for signal in assigned_signals
    )


def _set_step_expects_bms_response(step: dict, requirement_text: str) -> bool:
    action = str(step.get("action") or "")
    expected = str(step.get("expected") or "")
    if not expected.strip() or not _SET_ACTION_RE.search(action):
        return False

    action_ids = {m.group(0).lower() for m in _CODE_IDENTIFIER_RE.finditer(action)}
    expected_ids = {m.group(0) for m in _CODE_IDENTIFIER_RE.finditer(expected)}
    supported_ids = {
        m.group(0).lower()
        for m in _CODE_IDENTIFIER_RE.finditer(requirement_text)
    }
    for expected_id in expected_ids:
        expected_id_lower = expected_id.lower()
        if expected_id_lower in supported_ids and expected_id_lower not in action_ids:
            return True

    natural_response_patterns = [
        r"\bfault\b.*\bset\b",
        r"\bflag\b.*\b(?:set|active|asserted)\b",
        r"\bcharging\s+is\s+prevented\b",
        r"\bdischarge\s+power\s+is\s+limited\b",
        r"\bbalancing\s+is\s+suspended\b",
        r"\bcontactor\b.*\b(?:open|closed|prohibited)\b",
    ]
    return any(re.search(pattern, expected, re.IGNORECASE) for pattern in natural_response_patterns)


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
    rr = case.get("related_requirement", "").strip()

    signals = [s.strip() for s in req_info.get("signals", []) if s.strip()]
    thresholds = [t.strip() for t in req_info.get("thresholds", []) if t.strip()]
    timing = [t.strip() for t in req_info.get("timing", []) if t.strip() and t.strip().lower() != "none found"]
    expected_missing = req_info.get("expected_missing_categories", [])

    all_expected = " ".join([s["expected"] or "" for s in steps]).lower()
    all_step_text = " ".join(
        f"{s['action']} {s.get('expected') or ''}" for s in steps
    ).lower()

    steps_lower = "".join(
        s["action"] + (s.get("expected") or "")
        for s in steps
    ).lower()
    non_step_fields = f"{title} {obj} {pre} {post}".lower()
    has_needs_review = "[needs review]" in f"{non_step_fields} {steps_lower}"

    req_desc = req_info.get("requirement_description", "").lower()
    accepted_raw = req_info.get("accepted_test_basis", [])
    if isinstance(accepted_raw, str):
        accepted_test_basis = accepted_raw.lower()
    else:
        accepted_test_basis = " ".join(str(item) for item in accepted_raw).lower()

    # ── 1.1.1 ────────────────────────────────────────────────────────
    if not title or title.lower() in {"draft test case", "test case", "boundary test"}:
        failed.append("1.1.1")
    # ── 1.1.2 ────────────────────────────────────────────────────────
    if not obj:
        failed.append("1.1.2")
    # ── 1.1.3 ────────────────────────────────────────────────────────
    if not pre:
        failed.append("1.1.3")
    # ── 1.1.4 ────────────────────────────────────────────────────────
    if not post:
        failed.append("1.1.4")
    # ── 1.1.5 ────────────────────────────────────────────────────────
    if not steps:
        failed.append("1.1.5")
    else:
        has_action = any(s["action"].strip() for s in steps)
        has_expected = any((s["expected"] or "").strip() and (s["expected"] or "").strip().lower() not in ("null", "none") for s in steps)
        if not has_action or not has_expected:
            failed.append("1.1.5")
    # ── 1.1.6 ────────────────────────────────────────────────────────
    if not rr:
        failed.append("1.1.6")

    # ── 2.1.1 ────────────────────────────────────────────────────────
    if signals and all_expected and "[needs review]" not in all_expected:
        # Strip punctuation from expected text for matching
        clean_expected = re.sub(r"[,.:;!?，。：；！？]", " ", all_expected)
        if not any(re.sub(r"[,.:;!?，。：；！？]", " ", s.lower()) in clean_expected for s in signals):
            failed.append("2.1.1")

    # ── 2.1.2 ────────────────────────────────────────────────────────
    unsupported_step_ids = _unsupported_identifiers(
        all_step_text,
        req_info.get("requirement_description", ""),
        accepted_test_basis,
    )
    if unsupported_step_ids:
        failed.append("2.1.2")

    # ── 2.2.1 ────────────────────────────────────────────────────────
    # Supplementary context is human review reference, not generation authority.
    # Concrete numeric values must come from the selected requirement or an
    # explicitly accepted test basis.
    known_text = req_desc + " " + accepted_test_basis
    for step in steps:
        text = f"{step['action']} {step['expected'] or ''}"
        found_nums = [match.group(0) for match in _NUMERIC_VALUE_RE.finditer(text)]
        for num in found_nums:
            if not _is_supported_numeric_value(num, known_text):
                failed.append("2.2.1")
                break
        else:
            continue
        break

    # ── 3.2.1 ────────────────────────────────────────────────────────
    if expected_missing:
        nr_in_steps = any(
            "[needs review]" in (s["action"] + str(s["expected"] or "")).lower()
            for s in steps
        )
        if not nr_in_steps:
            failed.append("3.2.1")

    # ── 3.2.2 ────────────────────────────────────────────────────────
    if expected_missing:
        if "threshold" in expected_missing:
            for step in steps:
                text = f"{step['action']} {step['expected'] or ''}"
                found_nums = [match.group(0) for match in _NUMERIC_VALUE_RE.finditer(text)]
                invented_nums = [
                    num for num in found_nums
                    if not _is_supported_numeric_value(num, known_text)
                ]
                if invented_nums and "[needs review]" not in text.lower():
                    failed.append("3.2.2")
                    break

    # ── 3.2.3 ────────────────────────────────────────────────────────
    if has_needs_review and not expected_missing:
        failed.append("3.2.3")

    # ── 3.3.1 ────────────────────────────────────────────────────────
    nr_in_non_step = "[needs review]" in non_step_fields
    if nr_in_non_step:
        failed.append("3.3.1")

    # ── 3.3.2 ────────────────────────────────────────────────────────
    needs_review_in_steps = any(
        "[needs review]" in (s["action"] + str(s["expected"] or "")).lower()
        for s in steps
    )
    if "timing" in expected_missing and needs_review_in_steps:
        # Timing placeholder must be a standalone Wait step:
        # action contains "wait" AND "[needs review]". The wait step may also
        # carry the response expected result that becomes judgeable after wait.
        has_dedicated_wait_nr = any(
            "wait" in s["action"].lower()
            and "[needs review]" in s["action"].lower()
            for s in steps
        )
        if not has_dedicated_wait_nr:
            failed.append("3.3.2")

    # ── 3.3.3 ────────────────────────────────────────────────────────
    nr_with_suffix_pattern = re.compile(
        r"\[needs review\s*:\s*\w+\]", re.IGNORECASE
    )
    if nr_with_suffix_pattern.search(case.get("raw_html", "")) or nr_with_suffix_pattern.search(steps_lower):
        warnings.append("3.3.3")

    # ── 4.1.1 ────────────────────────────────────────────────────────
    if any(
        _set_step_expects_bms_response(step, req_info.get("requirement_description", ""))
        for step in steps
    ):
        failed.append("4.1.1")

    # ── 4.1.4 ────────────────────────────────────────────────────────
    intent_patterns = ["such that", "in order to", "to verify", "to ensure",
                       "to check", "so that", "to confirm", "to validate"]
    observe_verbs = ["check", "verify", "observe", "monitor", "capture"]
    for step in steps:
        action = step["action"].strip().lower()
        if any(pattern in action for pattern in intent_patterns):
            failed.append("4.1.4")
            break
        # Also check for observation verbs in action
        if any(verb in action.split() for verb in observe_verbs):
            failed.append("4.1.4")
            break

    # ── 4.2.2 ────────────────────────────────────────────────────────
    for step in steps:
        expected = (step["expected"] or "").lower()
        if expected and any(v in expected for v in ["system works correctly", "behaves as expected", "works as expected"]):
            failed.append("4.2.2")
            break

    # ── 4.2.3 ────────────────────────────────────────────────────────
    for step in steps:
        expected = (step["expected"] or "").lower()
        if expected:
            if _only_needs_review(expected):
                failed.append("4.2.3")
                break
            # Skip if expected uses [NEEDS REVIEW] placeholder with preserved
            # requirement behavior, for example "charging is prevented
            # [NEEDS REVIEW]".
            if "[needs review]" in expected:
                continue
            observe_words = ["read", "check", "verify", "observe", "monitor", "capture"]
            if any(v in expected.split() for v in observe_words):
                # Expected is only observation verbs without concrete value
                if len(expected.split()) < 8:
                    failed.append("4.2.3")
                    break

    # ── 5.1.1 ────────────────────────────────────────────────────────
    if (
        _contradicts_trigger_boundary(steps, req_info.get("requirement_description", ""))
        or _contradicts_response_time_bound(steps, req_info.get("requirement_description", ""))
    ):
        failed.append("5.1.1")

    # ── 6.1.3 ────────────────────────────────────────────────────────
    for step in steps:
        action = step["action"].strip().lower()
        if any(p in action for p in ["bms shall", "bms initiates", "bms verifies",
                                     "bms injects", "bms should", "bms performs"]):
            failed.append("6.1.3")
            break

    # ── 6.2.1 ────────────────────────────────────────────────────────
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
        "accepted_test_basis": req.get("accepted_test_basis", ""),
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
