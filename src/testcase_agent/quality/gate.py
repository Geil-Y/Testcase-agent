"""Development-time quality gate. Runtime keeps only schema + safety checks."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..parser.html_parser import GeneratedCase


@dataclass
class QualityReport:
    case_index: int
    passed: bool = False
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_RISKY_TERMS = (
    "real hil bench", "physical bench", "high-voltage activation",
    "hv activation", "energize high voltage", "close the real contactor",
    "open the real contactor", "destructive fault injection",
)


def evaluate_case(case: GeneratedCase, case_index: int = 0) -> QualityReport:
    report = QualityReport(case_index=case_index)

    # Schema: required fields
    if not case.title:
        report.failures.append("title is empty")
    if not case.objective:
        report.failures.append("objective is empty")
    if not case.precondition:
        report.failures.append("precondition is empty")
    if not case.postcondition:
        report.failures.append("postcondition is empty")
    if not case.steps:
        report.failures.append("no steps defined")

    for i, step in enumerate(case.steps, start=1):
        if not step.action:
            report.failures.append(f"step[{i}] action is empty")

    # Safety: no risky real-bench commands
    case_text = f"{case.title} {case.objective} {case.precondition} {case.postcondition}"
    for step in case.steps:
        case_text += f" {step.action} {step.expected or ''}"
    case_lower = case_text.lower()
    for term in _RISKY_TERMS:
        if term in case_lower:
            report.failures.append(f"safety: contains risky term '{term}'")

    # Warnings
    if case.title.strip().lower() in {"draft test case", "test case", "boundary test"}:
        report.warnings.append("title is generic, consider a descriptive title")

    if not _looks_english(case_text):
        report.warnings.append("content may not be in English")

    report.passed = len(report.failures) == 0
    return report


def evaluate_cases(cases: list[GeneratedCase]) -> list[QualityReport]:
    return [evaluate_case(case, i) for i, case in enumerate(cases)]


def _looks_english(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    ascii_letters = [c for c in letters if c.isascii()]
    return len(ascii_letters) / len(letters) >= 0.85
