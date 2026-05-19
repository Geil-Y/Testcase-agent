"""Post-processing sanitizers for LLM-generated test cases."""

from __future__ import annotations

import re
from copy import deepcopy

from ..parser.html_parser import GeneratedCase, Step

# Numbers with physical units the 7B model commonly invents
_NUMERIC_VALUE_RE = re.compile(
    r"\d+\.?\d*\s*(?:deg\s*C|°C|kOhm|MOhm|mOhm|kΩ|MΩ|mΩ|mV|mA|ms|ohm|Ω|deg|V|A|s|%)(?!\w)",
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
    replaced: list[str] = []
    result = text
    for match in pattern.finditer(text):
        if match.group().lower() not in known_text:
            result = result.replace(match.group(), "[NEEDS REVIEW]", 1)
            replaced.append(match.group())
    return result, replaced
