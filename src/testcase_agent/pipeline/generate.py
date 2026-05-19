from __future__ import annotations

from dataclasses import dataclass, field

from ..parser.html_parser import AnalysisResult, GeneratedCase, parse_analysis, parse_generated_case
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
    cases: list[GeneratedCase] = field(default_factory=list)
    error: str = ""


def run_pipeline(requirement: RequirementInput, provider: LlmProvider) -> GenerationResult:
    result = GenerationResult()

    # LLM#1: analyze + plan
    sys1, usr1 = render_prompt(
        "analyze_and_plan",
        requirement_key=requirement.requirement_key,
        description=requirement.description,
        function_name=requirement.function_name,
        supplementary_info=requirement.supplementary_info,
    )
    html1 = provider.complete(sys1, usr1)
    analysis = parse_analysis(html1)
    result.analysis = analysis

    if not analysis.case_intents:
        result.error = "LLM#1 produced no case intents"
        return result

    # LLM#2: generate one case per intent, with LLM#1's analysis as context
    signals_str = ", ".join(analysis.signals) if analysis.signals else ""
    thresholds_str = ", ".join(analysis.thresholds) if analysis.thresholds else ""
    timing_str = ", ".join(analysis.timing) if analysis.timing else ""
    missing_str = ", ".join(analysis.missing_critical_info) if analysis.missing_critical_info else ""

    for intent in analysis.case_intents:
        sys2, usr2 = render_prompt(
            "generate_case",
            requirement_key=requirement.requirement_key,
            description=requirement.description,
            supplementary_info=requirement.supplementary_info,
            coverage_dimension=intent.coverage,
            case_intent=intent.description,
            review_comment="",
            extracted_signals=signals_str,
            extracted_thresholds=thresholds_str,
            extracted_timing=timing_str,
            missing_info=missing_str,
        )
        html2 = provider.complete(sys2, usr2)
        case = parse_generated_case(html2)
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
) -> GeneratedCase:
    signals_str = ", ".join(analysis.signals) if analysis and analysis.signals else ""
    thresholds_str = ", ".join(analysis.thresholds) if analysis and analysis.thresholds else ""
    timing_str = ", ".join(analysis.timing) if analysis and analysis.timing else ""
    missing_str = ", ".join(analysis.missing_critical_info) if analysis and analysis.missing_critical_info else ""

    sys2, usr2 = render_prompt(
        "generate_case",
        requirement_key=requirement.requirement_key,
        description=requirement.description,
        supplementary_info=requirement.supplementary_info,
        coverage_dimension=coverage_dimension,
        case_intent=case_intent,
        review_comment=review_comment,
        extracted_signals=signals_str,
        extracted_thresholds=thresholds_str,
        extracted_timing=timing_str,
        missing_info=missing_str,
    )
    html2 = provider.complete(sys2, usr2)
    return parse_generated_case(html2)
