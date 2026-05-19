from __future__ import annotations

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
class AnalysisResult:
    signals: list[str] = field(default_factory=list)
    thresholds: list[str] = field(default_factory=list)
    timing: list[str] = field(default_factory=list)
    direction: str = ""
    missing_critical_info: list[str] = field(default_factory=list)
    case_intents: list[CaseIntent] = field(default_factory=list)
    raw_html: str = ""


def parse_analysis(html: str) -> AnalysisResult:
    soup = BeautifulSoup(html, "lxml")
    result = AnalysisResult(raw_html=html)

    analysis = soup.find("analysis")
    if analysis:
        for section in analysis.find_all("section"):
            name = section.get("name", "")
            text = section.get_text(strip=True)
            if name == "extracted_signals":
                result.signals = _lines(text)
            elif name == "extracted_thresholds":
                result.thresholds = _lines(text)
            elif name == "extracted_timing":
                result.timing = _lines(text)
            elif name == "extracted_direction":
                result.direction = text
            elif name == "missing_critical_info":
                result.missing_critical_info = _lines(text)

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
            order = int(step_el.get("order", 0))
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
