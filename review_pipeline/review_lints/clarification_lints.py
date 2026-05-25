"""Deterministic lints for clarification review artifacts."""

from __future__ import annotations

import re

from review_pipeline.artifacts.models import ClarificationReview, ReviewLint


SYMBOLIC_PARAMETER_RULE_ID = "symbolic_parameter_treated_as_missing"
EXPLICIT_EXPECTED_BEHAVIOR_RULE_ID = "explicit_expected_behavior_treated_as_ambiguity"

_PARAMETER_RE = re.compile(r"\b[A-Za-z]_[A-Za-z0-9_]+\b")
_VALUE_CUE_RE = re.compile(
    r"\b("
    r"exact|concrete|specific|numeric|value|duration|seconds?|milliseconds?|ms|unit|"
    r"threshold|timing|missing"
    r")\b",
    re.IGNORECASE,
)
_EXPLICIT_EXPECTED_BEHAVIOR_RE = re.compile(
    r"("
    r"\bshall\b|:=|\bshall\s+remain\b|\bshall\s+reset\b|"
    r"\bshall\s+open\b|\bshall\s+close\b|\bshall\s+be\b|"
    r"\bno\s+.+\bshall\s+be\s+stored\b|"
    r"\bdisabled\b|\bprohibited\b|\bopened\b|\bclosed\b"
    r")",
    re.IGNORECASE,
)
_CLEAR_TIMING_REFERENCE_RE = re.compile(
    r"\bwithin\s+\d+(?:\.\d+)?\s*(?:ms|s|seconds?|milliseconds?)\s+of\b",
    re.IGNORECASE,
)
_EXPECTED_BEHAVIOR_QUESTION_RE = re.compile(
    r"("
    r"\bwhat\s+is\s+the\s+(?:expected|exact|specific)\b|"
    r"\bis\s+.+\bor\s+from\s+some\s+other\s+event\b|"
    r"\bis\s+.+\bor\s+from\s+some\s+other\s+point\s+in\s+time\b|"
    r"\bis\s+.+\bor\s+is\s+it\s+.+\bafter\b|"
    r"\brelative\s+to\s+some\s+other\s+event\b|"
    r"\bwhat\s+specific\s+event\s+triggers\b|"
    r"\bwhat\s+.+\boutcome\b|"
    r"\bwhat\s+.+\bvalue\b"
    r")",
    re.IGNORECASE,
)


def lint_clarification_review(review: ClarificationReview) -> list[ReviewLint]:
    """Return deterministic warnings for suspicious LLM-A decomposition output."""
    requirement_symbols = _extract_requirement_symbols(review)
    lints: list[ReviewLint] = []

    for ambiguity in review.decomposition.ambiguities:
        ambiguity_text = " ".join(
            [
                ambiguity.affected_text,
                ambiguity.impact,
                ambiguity.clarification_question,
                ambiguity.safe_generation_policy,
                " ".join(ambiguity.reasons),
            ]
        )
        if not _VALUE_CUE_RE.search(ambiguity_text):
            continue

        for symbol in sorted(requirement_symbols):
            if not _contains_symbol(ambiguity_text, symbol):
                continue
            lints.append(
                ReviewLint(
                    rule_id=SYMBOLIC_PARAMETER_RULE_ID,
                    target_item_id=ambiguity.item_id,
                    symbol=symbol,
                    message=(
                        f"LLM-A may be treating symbolic parameter '{symbol}' as missing "
                        "because it lacks a concrete numeric value."
                    ),
                    evidence=[
                        "Symbol appears in requirement facts/source text.",
                        "Ambiguity asks for a concrete value, duration, unit, or threshold.",
                    ],
                )
            )
            break

        expected_behavior_lint = _lint_explicit_expected_behavior(ambiguity)
        if expected_behavior_lint:
            lints.append(expected_behavior_lint)

    return lints


def _lint_explicit_expected_behavior(ambiguity) -> ReviewLint | None:
    text = " ".join(
        [
            ambiguity.affected_text,
            ambiguity.impact,
            ambiguity.clarification_question,
            " ".join(ambiguity.reasons),
        ]
    )
    if not _EXPLICIT_EXPECTED_BEHAVIOR_RE.search(ambiguity.affected_text):
        return None
    if not _EXPECTED_BEHAVIOR_QUESTION_RE.search(text):
        return None
    if not _has_clear_behavior_target(ambiguity.affected_text):
        return None
    return ReviewLint(
        rule_id=EXPLICIT_EXPECTED_BEHAVIOR_RULE_ID,
        target_item_id=ambiguity.item_id,
        message=(
            "LLM-A may be treating explicit expected behavior as an ambiguity "
            "even though the requirement states the behavior or timing reference."
        ),
        evidence=[
            "Affected text contains explicit expected behavior wording.",
            "Clarification question asks for an outcome or timing reference already stated by the requirement.",
        ],
    )


def _has_clear_behavior_target(text: str) -> bool:
    if _CLEAR_TIMING_REFERENCE_RE.search(text):
        return True
    if _PARAMETER_RE.search(text):
        return True
    if re.search(r"\b(?:charge|discharge|main|fault|debounce|timer|flag|record|contactor|state)\b", text, re.IGNORECASE):
        return True
    return False


def _extract_requirement_symbols(review: ClarificationReview) -> set[str]:
    text_parts: list[str] = []
    for fact in review.decomposition.facts:
        text_parts.append(fact.fact_text)
        text_parts.append(fact.source_text)
    return set(_PARAMETER_RE.findall(" ".join(text_parts)))


def _contains_symbol(text: str, symbol: str) -> bool:
    return re.search(rf"\b{re.escape(symbol)}\b", text) is not None
