from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup


@dataclass
class Step:
    order: int
    action: str
    expected: str | None


@dataclass
class GeneratedCase:
    title: str
    objective: str
    precondition: str
    postcondition: str
    related_requirement: str = ""
    steps: list[Step] = field(default_factory=list)
    raw_html: str = ""


@dataclass
class CaseIntent:
    coverage: str
    description: str


@dataclass
class MissingInfo:
    category: str = ""
    description: str = ""


@dataclass
class AnalysisResult:
    signals: list[str] = field(default_factory=list)
    thresholds: list[str] = field(default_factory=list)
    timing: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)
    direction: str = ""
    missing_critical_info: list[str] = field(default_factory=list)
    missing_info_items: list[MissingInfo] = field(default_factory=list)
    case_intents: list[CaseIntent] = field(default_factory=list)
    raw_html: str = ""


def parse_analysis(html: str) -> AnalysisResult:
    soup = BeautifulSoup(html, "lxml")
    result = AnalysisResult(raw_html=html)

    analysis = soup.find("analysis")
    if analysis:
        for section in analysis.find_all("section"):
            name = section.get("name", "")
            if name == "extracted_direction":
                result.direction = section.get_text(strip=True)
            else:
                items = [it.get_text(strip=True) for it in section.find_all("item")]
                value = items if items else _lines(section.get_text(strip=True))
                if name == "extracted_signals":
                    result.signals = value
                elif name == "extracted_thresholds":
                    result.thresholds = value
                elif name == "extracted_timing":
                    result.timing = value
                elif name == "extracted_states":
                    result.states = value
                elif name == "extracted_observations":
                    result.observations = value
                elif name == "missing_critical_info":
                    result.missing_info_items = _parse_missing_items(section)
                    result.missing_critical_info = [m.description for m in result.missing_info_items]

    plan = soup.find("coverage_plan")
    if plan:
        for el in plan.find_all("case_intent"):
            intent = CaseIntent(
                coverage=el.get("coverage", "normal_behavior"),
                description=el.get_text(strip=True),
            )
            result.case_intents.append(intent)

    return result


def parse_generated_case(html: str) -> GeneratedCase:
    soup = BeautifulSoup(html, "lxml")
    case_el = soup.find("testcase")
    result = GeneratedCase(title="", objective="", precondition="", postcondition="", raw_html=html)

    if case_el is None:
        return result

    title_el = case_el.find("title")
    if title_el:
        result.title = title_el.get_text(strip=True)

    obj_el = case_el.find("objective")
    if obj_el:
        result.objective = obj_el.get_text(strip=True)

    pre_el = case_el.find("precondition")
    if pre_el:
        result.precondition = pre_el.get_text(strip=True)

    post_el = case_el.find("postcondition")
    if post_el:
        result.postcondition = post_el.get_text(strip=True)

    rr_el = case_el.find("related_requirement")
    if rr_el:
        result.related_requirement = rr_el.get_text(strip=True)

    steps_el = case_el.find("steps")
    if steps_el:
        for step_el in steps_el.find_all("step"):
            try:
                order = int(step_el.get("order", 0))
            except (ValueError, TypeError):
                # Malformed order attribute — extract digits or fall back
                raw = step_el.get("order", "0")
                m = re.search(r"\d+", str(raw))
                order = int(m.group()) if m else 0
            action = ""
            expected = None
            action_el = step_el.find("action")
            if action_el:
                action = action_el.get_text(strip=True)
            expected_el = step_el.find("expected")
            if expected_el:
                text = expected_el.get_text(strip=True)
                expected = text if text.lower() != "null" else None
            result.steps.append(Step(order=order, action=action, expected=expected))

    return result


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and line.strip().lower() != "none found"]


def _parse_missing_items(section) -> list[MissingInfo]:
    """Extract MissingInfo from a <section name='missing_critical_info'> element.

    Supports both old and new formats:
      - <item>description</item>                → category=""
      - <item category="timing">description</item>  → category="timing"
    """
    result: list[MissingInfo] = []
    for item_el in section.find_all("item"):
        desc = item_el.get_text(strip=True)
        if desc and desc.lower() not in ("none", "none found"):
            category = item_el.get("category", "")
            result.append(MissingInfo(category=category, description=desc))
    return result
