from __future__ import annotations

from dataclasses import dataclass, field

from ..parser.html_parser import AnalysisResult, GeneratedCase, parse_generated_case
from ..parser.json_parser import (
    CaseIntentPlan,
    MissingInfoItem,
    TestBasis,
    parse_case_intents_json,
    parse_test_basis_json,
)
from ..prompts import render_prompt
from ..provider.base import LlmProvider


@dataclass
class RequirementInput:
    requirement_key: str
    description: str
    function_name: str = ""
    supplementary_info: str = ""


@dataclass
class GenerationResult:
    analysis: AnalysisResult | None = None
    test_basis: TestBasis | None = None
    intent_plan: CaseIntentPlan | None = None
    cases: list[GeneratedCase] = field(default_factory=list)
    error: str = ""
    generation_failures: list[int] = field(default_factory=list)


def run_pipeline(requirement: RequirementInput, provider: LlmProvider) -> GenerationResult:
    result = GenerationResult()

    # ── LLM-A: analyze test basis → JSON ────────────────────────────────
    sys_a, usr_a = render_prompt(
        "analyze_test_basis",
        requirement_key=requirement.requirement_key,
        description=requirement.description,
    )
    try:
        raw_a = provider.complete(sys_a, usr_a)
        test_basis = parse_test_basis_json(raw_a)
    except Exception as e:
        result.error = f"LLM-A failed: {e}"
        return result
    result.test_basis = test_basis

    # ── LLM-B: plan case intents → JSON ─────────────────────────────────
    missing_info_json = _format_missing_info_json(test_basis.missing_info)

    sys_b, usr_b = render_prompt(
        "plan_case_intents",
        requirement_key=requirement.requirement_key,
        description=requirement.description,
        allowed_signals=_format_list(test_basis.allowed_signals),
        allowed_thresholds=_format_list(test_basis.allowed_thresholds),
        allowed_timing=_format_list(test_basis.allowed_timing),
        allowed_states=_format_list(test_basis.allowed_states),
        allowed_observations=_format_list(test_basis.allowed_observations),
        missing_info=missing_info_json,
    )
    try:
        raw_b = provider.complete(sys_b, usr_b)
        intent_plan = parse_case_intents_json(raw_b)
    except Exception as e:
        result.error = f"LLM-B failed: {e}"
        return result
    result.intent_plan = intent_plan

    if not intent_plan.case_intents:
        result.error = "LLM-B produced no case intents"
        return result

    # ── LLM-C: generate one case per intent → HTML ──────────────────────
    signals_str = ", ".join(test_basis.allowed_signals)
    thresholds_str = ", ".join(test_basis.allowed_thresholds)
    timing_str = ", ".join(test_basis.allowed_timing)
    states_str = ", ".join(test_basis.allowed_states)
    observations_str = ", ".join(test_basis.allowed_observations)
    missing_str = ", ".join(mi.description for mi in test_basis.missing_info)
    missing_items_str = _format_missing_items_prompt(test_basis.missing_info)

    for i, intent in enumerate(intent_plan.case_intents):
        sys_c, usr_c = render_prompt(
            "generate_case",
            requirement_key=requirement.requirement_key,
            description=requirement.description,
            supplementary_info="",
            coverage_dimension=intent.coverage_dimension,
            case_intent=intent.intent_text,
            review_comment="",
            extracted_signals=signals_str,
            extracted_thresholds=thresholds_str,
            extracted_timing=timing_str,
            extracted_states=states_str,
            extracted_observations=observations_str,
            missing_info=missing_str,
            missing_info_items=missing_items_str,
        )
        try:
            html_c = provider.complete(sys_c, usr_c)
            case = parse_generated_case(html_c)
            if "<testcase>" not in html_c:
                raise ValueError("LLM-C output missing <testcase> tag")
        except Exception:
            case = GeneratedCase(
                title=intent.intent_text[:80],
                objective=intent.intent_text,
                precondition="",
                postcondition="",
                steps=[],
                raw_html="",
            )
            result.generation_failures.append(i)
        result.cases.append(case)

    return result


def regenerate_case(
    requirement: RequirementInput,
    case_intent: str,
    coverage_dimension: str,
    review_comment: str,
    provider: LlmProvider,
    *,
    analysis: AnalysisResult | None = None,
    test_basis: TestBasis | None = None,
) -> GeneratedCase:
    if test_basis is not None:
        signals_str = ", ".join(test_basis.allowed_signals)
        thresholds_str = ", ".join(test_basis.allowed_thresholds)
        timing_str = ", ".join(test_basis.allowed_timing)
        states_str = ", ".join(test_basis.allowed_states)
        observations_str = ", ".join(test_basis.allowed_observations)
        missing_str = ", ".join(mi.description for mi in test_basis.missing_info)
        missing_items_str = _format_missing_items_prompt(test_basis.missing_info)
    elif analysis is not None:
        signals_str = ", ".join(analysis.signals)
        thresholds_str = ", ".join(analysis.thresholds)
        timing_str = ", ".join(analysis.timing)
        states_str = ", ".join(analysis.states)
        observations_str = ", ".join(analysis.observations)
        missing_str = ", ".join(analysis.missing_critical_info)
        missing_items_str = _format_missing_items_legacy(analysis)
    else:
        signals_str = thresholds_str = timing_str = states_str = observations_str = ""
        missing_str = missing_items_str = ""

    sys2, usr2 = render_prompt(
        "generate_case",
        requirement_key=requirement.requirement_key,
        description=requirement.description,
        supplementary_info="",
        coverage_dimension=coverage_dimension,
        case_intent=case_intent,
        review_comment=review_comment,
        extracted_signals=signals_str,
        extracted_thresholds=thresholds_str,
        extracted_timing=timing_str,
        extracted_states=states_str,
        extracted_observations=observations_str,
        missing_info=missing_str,
        missing_info_items=missing_items_str,
    )
    try:
        html2 = provider.complete(sys2, usr2)
        return parse_generated_case(html2)
    except Exception:
        return GeneratedCase(
            title=case_intent[:80],
            objective=case_intent,
            steps=[],
            raw_html="",
        )


# ── helpers ──────────────────────────────────────────────────────────────

def _format_list(items: list[str]) -> str:
    return ", ".join(items)


def _format_missing_info_json(items: list[MissingInfoItem]) -> str:
    """Render missing_info as a compact JSON-like string for prompt injection."""
    if not items:
        return "[]"
    parts = [f'{{"category": "{mi.category}", "description": "{mi.description}"}}' for mi in items]
    return "[" + ", ".join(parts) + "]"


def _format_missing_items_prompt(items: list[MissingInfoItem]) -> str:
    """Format categorized missing info items for prompt rendering."""
    if not items:
        return ""
    lines: list[str] = []
    for item in items:
        if item.category:
            lines.append(f"[{item.category}] {item.description}")
        else:
            lines.append(item.description)
    return "\n".join(lines)


def _format_missing_items_legacy(analysis: AnalysisResult) -> str:
    """Format categorized missing info items from legacy AnalysisResult."""
    if not analysis.missing_info_items:
        return ""
    lines: list[str] = []
    for item in analysis.missing_info_items:
        if item.category:
            lines.append(f"[{item.category}] {item.description}")
        else:
            lines.append(item.description)
    return "\n".join(lines)
