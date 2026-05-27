"""Deterministic confidence aggregation and color routing.

LLMs provide driver scores and reasons. Code only aggregates, maps to
routing color, and applies bounded historical adjustment.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Confidence drivers ─────────────────────────────────────────────────────

CLARIFICATION_DRIVERS = [
    "trigger_clarity",
    "expected_behavior_clarity",
    "known_info_sufficiency",
    "ambiguity_resolution",
    "historical_pattern_support",
]

CASE_INTENT_DRIVERS = [
    "requirement_basis_strength",
    "separate_case_value",
    "missing_info_handling",
    "historical_decision_support",
]

# ── Routing thresholds ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class RoutingLevel:
    color: str
    label: str
    lower: float  # inclusive
    upper: float  # exclusive; 1.01 means "no upper bound"

ROUTING_TABLE = [
    RoutingLevel("green",  "",        0.85, 1.01),
    RoutingLevel("blue",   "",        0.65, 0.85),
    RoutingLevel("orange", "",        0.40, 0.65),
    RoutingLevel("red",    "",        0.00, 0.40),
]

CLARIFICATION_LABELS = {
    "green":  "Clear",
    "blue":   "Minor ambiguity",
    "orange": "Review required",
    "red":    "Clarification required",
}

CASE_INTENT_LABELS = {
    "green":  "Strong intent",
    "blue":   "Review recommended",
    "orange": "Review required",
    "red":    "Do not generate yet",
}

# ── Historical adjustment bounds ───────────────────────────────────────────

HISTORICAL_ADJUSTMENT_MIN = -0.10
HISTORICAL_ADJUSTMENT_MAX = +0.10

# Default for missing historical driver.
MISSING_DRIVER_DEFAULT = 0.5


# ── Public API ─────────────────────────────────────────────────────────────


def aggregate_confidence(drivers: dict[str, float], *, historical_adjustment: float = 0.0) -> float:
    """Compute average confidence from driver scores.

    Driver scores must be in [0.0, 1.0]. Missing drivers default to 0.5.
    Historical adjustment is clamped to [-0.10, +0.10].
    """
    all_driver_names = list(drivers.keys())
    scores: list[float] = []
    for name in all_driver_names:
        v = drivers.get(name, MISSING_DRIVER_DEFAULT)
        if v is None:
            v = MISSING_DRIVER_DEFAULT
        _validate_driver_score(name, v)
        scores.append(v)
    if not scores:
        return 0.5 + historical_adjustment
    avg = sum(scores) / len(scores)
    adj = _clamp(historical_adjustment, HISTORICAL_ADJUSTMENT_MIN, HISTORICAL_ADJUSTMENT_MAX)
    return _clamp(avg + adj, 0.0, 1.0)


def routing_for_confidence(confidence: float) -> RoutingLevel:
    """Map confidence score to routing level."""
    for r in ROUTING_TABLE:
        if r.lower <= confidence < r.upper:
            return r
    return ROUTING_TABLE[-1]  # red


def routing_label(confidence: float, is_clarification: bool) -> str:
    """Human-readable label for the routing color."""
    r = routing_for_confidence(confidence)
    labels = CLARIFICATION_LABELS if is_clarification else CASE_INTENT_LABELS
    return labels[r.color]


def normalize_historical_adjustment(raw: float) -> float:
    """Clamp historical adjustment to allowed bounds."""
    return _clamp(raw, HISTORICAL_ADJUSTMENT_MIN, HISTORICAL_ADJUSTMENT_MAX)


# ── Helpers ────────────────────────────────────────────────────────────────

def _validate_driver_score(name: str, value: float) -> None:
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"Driver '{name}' score {value} is out of range [0.0, 1.0]")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
