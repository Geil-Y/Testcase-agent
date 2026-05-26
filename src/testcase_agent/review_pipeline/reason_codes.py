"""Reason code registry loader.

Loads the canonical reason_codes.yml and provides lookup methods used by
validation, pattern tag derivation, and memory import.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _load_registry() -> dict[str, Any]:
    path = Path(__file__).resolve().parent / "reason_codes.yml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def get_registry() -> dict[str, Any]:
    return _load_registry()


def get_clarification_decisions() -> list[str]:
    return list(get_registry()["clarification_decisions"])


def get_case_intent_decisions() -> list[str]:
    return list(get_registry()["case_intent_decisions"])


def get_positive_reason_codes() -> list[str]:
    return list(get_registry()["positive_reason_codes"])


def get_negative_reason_codes() -> list[str]:
    return list(get_registry()["negative_reason_codes"])


def get_all_reason_codes() -> list[str]:
    r = get_registry()
    return list(r["positive_reason_codes"]) + list(r["negative_reason_codes"])


def get_reason_codes_for(item_type: str) -> list[str]:
    """Return valid reason codes for 'clarification_item' or 'case_intent_item'."""
    return list(get_registry()["reason_code_applicability"][item_type])


def get_decision_requirements(decision: str) -> dict[str, bool]:
    """Return {require_reason_code, require_reason_text} for a decision."""
    return dict(get_registry()["decision_requirements"].get(decision, {}))


def is_decision_valid(item_type: str, decision: str) -> bool:
    if item_type == "clarification_item":
        return decision in get_clarification_decisions()
    elif item_type == "case_intent_item":
        return decision in get_case_intent_decisions()
    return False


def is_reason_code_valid(item_type: str, code: str) -> bool:
    valid = get_reason_codes_for(item_type)
    return code in valid


def requires_reason_text_on_conflict() -> bool:
    return get_registry()["confidence_decision_conflict"]["require_reason_text"]


def get_conflict_threshold() -> float:
    return get_registry()["confidence_decision_conflict"]["conflict_threshold"]
