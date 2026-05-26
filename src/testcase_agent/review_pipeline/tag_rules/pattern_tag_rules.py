"""Deterministic pattern tag derivation.

Pattern tags are evidence-backed memory indexes derived by code, never by LLM
or direct human editing. Tags come from reason codes, ambiguity types, missing
info categories, coverage dimensions, and conservative text detectors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


# ── Tag registry ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TagDef:
    tag: str
    label: str
    description: str
    groups: list[str] = field(default_factory=list)
    allowed_sources: list[str] = field(default_factory=list)


@dataclass
class DerivedTag:
    tag: str
    tag_strength: str  # "confirmed" | "candidate"
    source: str  # reason_code | ambiguity_type | missing_category | coverage_dimension | text_detector
    rule_id: str
    evidence_text: str
    confidence: float = 1.0


# ── Registry loading ──────────────────────────────────────────────────────

def _load_registry() -> list[dict[str, Any]]:
    path = Path(__file__).resolve().parents[1] / "pattern_tags.yml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["tags"]


@lru_cache
def _tag_defs() -> dict[str, TagDef]:
    tags = _load_registry()
    return {t["tag"]: TagDef(**{k: t[k] for k in ["tag", "label", "description", "groups", "allowed_sources"]}) for t in tags}


def get_known_tags() -> set[str]:
    return set(_tag_defs().keys())


# ── Tag derivation ─────────────────────────────────────────────────────────

def derive_from_reason_codes(reason_codes: list[str]) -> list[DerivedTag]:
    """Derive confirmed tags from reason codes."""
    mapping = {
        "unsupported_by_requirement": "invented_behavior",
        "duplicate_expected_behavior": "duplicate_intent",
        "over_split_condition_combination": "over_split",
        "too_broad_to_verify": "too_broad",
        "needs_clarification": "needs_clarification",
        "valid_timing_maturity_case": "timing_maturity",
        "safe_to_generate_with_marker": "needs_clarification",
    }
    return _derive_from_map(reason_codes, mapping, "reason_code")


def derive_from_ambiguity_types(ambiguity_types: list[str]) -> list[DerivedTag]:
    """Derive confirmed tags from ambiguity types."""
    mapping = {
        "signal": "missing_signal",
        "threshold": "missing_threshold",
        "timing": "missing_timing",
        "state": "missing_state",
        "observation": "missing_observation",
    }
    # Add each type and also the raw form as fallback
    tags = _derive_from_map(ambiguity_types, mapping, "ambiguity_type")
    # Also add "needs_clarification" if any ambiguity exists
    if ambiguity_types:
        tags.append(DerivedTag(
            tag="needs_clarification",
            tag_strength="confirmed",
            source="ambiguity_type",
            rule_id="any_ambiguity",
            evidence_text=", ".join(ambiguity_types),
            confidence=0.9,
        ))
    return tags


def derive_from_missing_categories(categories: list[str]) -> list[DerivedTag]:
    """Derive confirmed tags from missing information categories."""
    mapping = {
        "signal": "missing_signal",
        "threshold": "missing_threshold",
        "timing": "missing_timing",
        "state": "missing_state",
        "observation": "missing_observation",
    }
    return _derive_from_map(categories, mapping, "missing_category")


def derive_from_coverage_dimensions(dimensions: list[str]) -> list[DerivedTag]:
    """Derive confirmed tags from coverage dimensions."""
    mapping = {
        "normal_behavior": "coverage_normal_behavior",
        "boundary_or_threshold": "coverage_boundary_threshold",
        "fault_or_protection": "coverage_fault_protection",
        "state_transition": "coverage_state_transition",
        "observability": "coverage_observability",
    }
    return _derive_from_map(dimensions, mapping, "coverage_dimension")


def derive_from_text_detectors(text: str) -> list[DerivedTag]:
    """Derive candidate tags only from conservative text detectors.

    Text detectors are candidate-only: they never act as authority.
    """
    detectors = [
        ("response_time_bound", "response_time_detector", [r"response\s*time", r"latency", r"within\s+\d+\s*ms", r"响应时间", r"延迟"]),
        ("timing_maturity", "timing_maturity_detector", [r"timing\s+maturity", r"specified\s+timing", r"时间要求"]),
        ("diagnostic_clear", "diagnostic_clear_detector", [r"diagnostic", r"fault\s+clear", r"故障清除", r"诊断"]),
        ("persistence", "persistence_detector", [r"persist", r"latch", r"NVM", r"存储", r"锁存"]),
        ("logging_record", "logging_record_detector", [r"log", r"record", r"event\s+storage", r"记录", r"日志"]),
    ]

    import re
    tags: list[DerivedTag] = []
    for tag_name, rule_id, patterns in detectors:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                tags.append(DerivedTag(
                    tag=tag_name,
                    tag_strength="candidate",
                    source="text_detector",
                    rule_id=rule_id,
                    evidence_text=pattern,
                    confidence=0.5,
                ))
                break  # one match per detector
    return tags


def derive_all_tags(
    *,
    reason_codes: list[str] | None = None,
    ambiguity_types: list[str] | None = None,
    missing_categories: list[str] | None = None,
    coverage_dimensions: list[str] | None = None,
    text: str = "",
) -> list[DerivedTag]:
    """Derive all tags from available evidence sources."""
    all_tags: list[DerivedTag] = []
    if reason_codes:
        all_tags.extend(derive_from_reason_codes(reason_codes))
    if ambiguity_types:
        all_tags.extend(derive_from_ambiguity_types(ambiguity_types))
    if missing_categories:
        all_tags.extend(derive_from_missing_categories(missing_categories))
    if coverage_dimensions:
        all_tags.extend(derive_from_coverage_dimensions(coverage_dimensions))
    if text:
        all_tags.extend(derive_from_text_detectors(text))
    return _deduplicate_tags(all_tags)


def reject_unknown_tags(tags: list[DerivedTag]) -> list[DerivedTag]:
    """Remove tags not in the registry. Unknown tags are silently dropped."""
    known = get_known_tags()
    return [t for t in tags if t.tag in known]


# ── Helpers ────────────────────────────────────────────────────────────────

def _derive_from_map(keys: list[str], mapping: dict[str, str], source: str) -> list[DerivedTag]:
    tags: list[DerivedTag] = []
    seen: set[str] = set()
    for key in keys:
        if key in mapping:
            tag_name = mapping[key]
            if tag_name not in seen:
                seen.add(tag_name)
                tags.append(DerivedTag(
                    tag=tag_name,
                    tag_strength="confirmed",
                    source=source,
                    rule_id=f"{source}_{key}",
                    evidence_text=key,
                    confidence=1.0,
                ))
    return tags


def _deduplicate_tags(tags: list[DerivedTag]) -> list[DerivedTag]:
    """Keep the highest-confidence entry per tag name."""
    best: dict[str, DerivedTag] = {}
    for t in tags:
        if t.tag not in best or t.confidence > best[t.tag].confidence:
            best[t.tag] = t
    return list(best.values())
