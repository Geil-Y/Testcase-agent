from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_VALID_MISSING_INFO_CATEGORIES = frozenset({
    "signal", "threshold", "timing", "state", "observation",
})

_VALID_COVERAGE_DIMENSIONS = frozenset({
    "normal_behavior",
    "boundary_or_threshold",
    "fault_or_protection",
    "state_transition",
    "observability",
})


@dataclass
class MissingInfoItem:
    category: str
    description: str


@dataclass
class TestBasis:
    __test__ = False  # prevent pytest collection — this is a dataclass, not a test
    requirement_key: str
    allowed_signals: list[str] = field(default_factory=list)
    allowed_thresholds: list[str] = field(default_factory=list)
    allowed_timing: list[str] = field(default_factory=list)
    allowed_states: list[str] = field(default_factory=list)
    allowed_observations: list[str] = field(default_factory=list)
    missing_info: list[MissingInfoItem] = field(default_factory=list)


@dataclass
class PlannedCaseIntent:
    intent_id: str
    coverage_dimension: str
    intent_text: str


@dataclass
class CaseIntentPlan:
    requirement_key: str
    case_intents: list[PlannedCaseIntent] = field(default_factory=list)


def _strip_fence(raw: str) -> str:
    """Strip ```json ... ``` fence if present."""
    text = raw.strip()
    m = re.match(r"```(?:json)?\s*\n(.*?)\n\s*```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def parse_test_basis_json(raw: str) -> TestBasis:
    text = _strip_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM-A JSON parse error: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("LLM-A output must be a JSON object")

    requirement_key = _require_str(data, "requirement_key")
    allowed_signals = _str_list(data.get("allowed_signals", []), "allowed_signals")
    allowed_thresholds = _str_list(data.get("allowed_thresholds", []), "allowed_thresholds")
    allowed_timing = _str_list(data.get("allowed_timing", []), "allowed_timing")
    allowed_states = _str_list(data.get("allowed_states", []), "allowed_states")
    allowed_observations = _str_list(data.get("allowed_observations", []), "allowed_observations")

    missing_info: list[MissingInfoItem] = []
    raw_missing = data.get("missing_info", [])
    if not isinstance(raw_missing, list):
        raise ValueError("missing_info must be a list")
    for i, item in enumerate(raw_missing):
        if not isinstance(item, dict):
            raise ValueError(f"missing_info[{i}] must be an object")
        category = _require_str(item, "category", f"missing_info[{i}].category")
        if category not in _VALID_MISSING_INFO_CATEGORIES:
            raise ValueError(
                f"missing_info[{i}].category must be one of "
                f"{sorted(_VALID_MISSING_INFO_CATEGORIES)}, got '{category}'"
            )
        description = _require_str(item, "description", f"missing_info[{i}].description")
        missing_info.append(MissingInfoItem(category=category, description=description))

    return TestBasis(
        requirement_key=requirement_key,
        allowed_signals=allowed_signals,
        allowed_thresholds=allowed_thresholds,
        allowed_timing=allowed_timing,
        allowed_states=allowed_states,
        allowed_observations=allowed_observations,
        missing_info=missing_info,
    )


def parse_case_intents_json(raw: str) -> CaseIntentPlan:
    text = _strip_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM-B JSON parse error: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("LLM-B output must be a JSON object")

    requirement_key = _require_str(data, "requirement_key")
    raw_intents = data.get("case_intents", [])
    if not isinstance(raw_intents, list):
        raise ValueError("case_intents must be a list")

    intents: list[PlannedCaseIntent] = []
    for i, item in enumerate(raw_intents):
        if not isinstance(item, dict):
            raise ValueError(f"case_intents[{i}] must be an object")
        intent_id = _require_str(item, "intent_id", f"case_intents[{i}].intent_id")
        coverage_dimension = _require_str(
            item, "coverage_dimension", f"case_intents[{i}].coverage_dimension"
        )
        if coverage_dimension not in _VALID_COVERAGE_DIMENSIONS:
            raise ValueError(
                f"case_intents[{i}].coverage_dimension must be one of "
                f"{sorted(_VALID_COVERAGE_DIMENSIONS)}, got '{coverage_dimension}'"
            )
        intent_text = _require_str(item, "intent_text", f"case_intents[{i}].intent_text")
        intents.append(PlannedCaseIntent(
            intent_id=intent_id,
            coverage_dimension=coverage_dimension,
            intent_text=intent_text,
        ))

    return CaseIntentPlan(requirement_key=requirement_key, case_intents=intents)


def _require_str(data: dict, key: str, label: str = "") -> str:
    val = data.get(key)
    if val is None:
        raise ValueError(f"{label or key} is required")
    if not isinstance(val, str):
        raise ValueError(f"{label or key} must be a string, got {type(val).__name__}")
    return val


def _str_list(val, label: str) -> list[str]:
    if not isinstance(val, list):
        raise ValueError(f"{label} must be a list")
    result: list[str] = []
    for i, item in enumerate(val):
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            result.append(_flatten_dict_item(item, label, i))
        else:
            result.append(str(item))
    return result


def _flatten_dict_item(item: dict, label: str, idx: int) -> str:
    """Extract a string from a dict where a plain string was expected."""
    for key in ("name", "signal", "threshold", "value", "description", "text"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            return v
    import json as _json
    return _json.dumps(item, ensure_ascii=False)
