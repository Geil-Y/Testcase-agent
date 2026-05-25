"""Deterministic lints for clarification review artifacts."""

from __future__ import annotations

import re

from review_pipeline.artifacts.models import ClarificationReview, ReviewLint


SYMBOLIC_PARAMETER_RULE_ID = "symbolic_parameter_treated_as_missing"

_PARAMETER_RE = re.compile(r"\b[A-Za-z]_[A-Za-z0-9_]+\b")
_VALUE_CUE_RE = re.compile(
    r"\b("
    r"exact|concrete|specific|numeric|value|duration|seconds?|milliseconds?|ms|unit|"
    r"threshold|timing|missing"
    r")\b",
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

    return lints


def _extract_requirement_symbols(review: ClarificationReview) -> set[str]:
    text_parts: list[str] = []
    for fact in review.decomposition.facts:
        text_parts.append(fact.fact_text)
        text_parts.append(fact.source_text)
    return set(_PARAMETER_RE.findall(" ".join(text_parts)))


def _contains_symbol(text: str, symbol: str) -> bool:
    return re.search(rf"\b{re.escape(symbol)}\b", text) is not None
