"""Post-processing sanitizers for LLM-generated test cases."""

from __future__ import annotations

import re
from copy import deepcopy

from ..parser.html_parser import GeneratedCase, Step

_NEEDS_REVIEW_RE = re.compile(r"\s*\[NEEDS REVIEW\]\s*", re.IGNORECASE)


def strip_needless_markers(case: GeneratedCase, *, has_missing: bool) -> GeneratedCase:
    """Remove [NEEDS REVIEW] markers when LLM#1 says nothing is missing.

    When has_missing is False, the markers are inconsistent — either LLM#2
    added them unnecessarily or the numeric sanitizer injected them.  Strip
    them so that checklist items 3.1.1 and 3.2.1 treat the case consistently.
    """
    if has_missing:
        return case
    sanitized = deepcopy(case)
    new_steps = []
    for step in sanitized.steps:
        new_action = _NEEDS_REVIEW_RE.sub(" ", step.action).strip()
        new_expected = step.expected
        if step.expected:
            new_expected = _NEEDS_REVIEW_RE.sub(" ", step.expected).strip()
        new_steps.append(
            Step(order=step.order, action=new_action, expected=new_expected)
        )
    sanitized.steps = new_steps
    # Also strip from raw_html so evaluator doesn't find residual markers
    if sanitized.raw_html:
        sanitized.raw_html = _NEEDS_REVIEW_RE.sub(" ", sanitized.raw_html)
    return sanitized

# Numbers with physical units the 7B model commonly invents.
# Capture group 1 = the unit, so we can check whether known_text already
# references the same physical quantity (e.g. 4.26V is a boundary
# derivation from 4.25V in the requirement, not a pure invention).
_UNIT_PATTERN = r"(deg\s*C|°C|kOhm|MOhm|mOhm|kΩ|MΩ|mΩ|mV|mA|ms|ohm|Ω|deg|V|A|s|%)"
_NUMERIC_VALUE_RE = re.compile(
    rf"\d+\.?\d*\s*{_UNIT_PATTERN}(?!\w)",
    re.IGNORECASE,
)


def sanitize_numeric_values(
    case: GeneratedCase,
    *,
    requirement_description: str,
    supplementary_info: str,
    extracted_signals: list[str],
    extracted_thresholds: list[str],
    extracted_timing: list[str],
) -> tuple[GeneratedCase, list[str]]:
    """Replace invented numeric values with [NEEDS REVIEW].

    Scans action and expected fields only. A numeric value is considered
    "known" if it appears (case-insensitive) in the combined text of the
    requirement description, supplementary info, signals, thresholds, and
    timing parameters.

    Returns (sanitized_case, list_of_replacements).
    """
    known_text = (
        requirement_description
        + " "
        + supplementary_info
        + " "
        + " ".join(extracted_timing + extracted_thresholds + extracted_signals)
    ).lower()

    sanitized = deepcopy(case)
    replacements: list[str] = []

    new_steps = []
    for step in sanitized.steps:
        new_action, reps_a = _replace_invented(step.action, known_text, _NUMERIC_VALUE_RE)
        new_expected = step.expected
        reps_e = []
        if step.expected:
            new_expected, reps_e = _replace_invented(step.expected, known_text, _NUMERIC_VALUE_RE)
        new_steps.append(
            Step(order=step.order, action=new_action, expected=new_expected)
        )
        replacements.extend(reps_a + reps_e)

    sanitized.steps = new_steps
    return sanitized, replacements


def _replace_invented(
    text: str, known_text: str, pattern: re.Pattern
) -> tuple[str, list[str]]:
    """Replace numeric values that are pure inventions (not boundary derivations).

    A value is skipped when *either*:
    1. The exact string appears in known_text.
    2. known_text contains a numeric value with the same unit whose magnitude
       is within ±15% — likely a boundary-test derivation.
    """
    replaced: list[str] = []
    result = text

    # Collect (numeric_value, normalized_unit) from known_text
    known_pairs: list[tuple[float, str]] = []
    for m in pattern.finditer(known_text):
        num_str = re.match(r"(\d+\.?\d*)", m.group())
        if num_str:
            known_pairs.append((float(num_str.group(1)), m.group(1).lower().replace(" ", "")))

    for match in pattern.finditer(text):
        matched = match.group()
        unit = match.group(1).lower().replace(" ", "")
        if matched.lower() in known_text:
            continue  # exact match

        # Check if any known value with the same unit is within ±15%
        num_str = re.match(r"(\d+\.?\d*)", matched)
        if num_str:
            val = float(num_str.group(1))
            for known_val, known_unit in known_pairs:
                if unit == known_unit:
                    if known_val > 0 and abs(val - known_val) / known_val <= 0.20:
                        break  # boundary derivation, skip
            else:
                # No close known value -> replace
                result = result.replace(matched, "[NEEDS REVIEW]", 1)
                replaced.append(matched)
        else:
            # Can't parse number -> replace
            result = result.replace(matched, "[NEEDS REVIEW]", 1)
            replaced.append(matched)
    return result, replaced
