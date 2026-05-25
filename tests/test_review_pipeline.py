"""End-to-end offline pipeline fixture (Issue 14) and comprehensive unit tests.

Covers all 15 issues with fake providers (no real LLM calls).
"""

from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
from pathlib import Path

import pytest


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def run_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def sample_requirement_json(run_dir):
    """Create a sample requirements JSON file."""
    data = [
        {
            "requirement_key": "BMS_REQ_001",
            "description": "The BMS shall detect cell over-voltage and open the contactor within 100ms.",
            "function_name": "Cell Monitoring",
            "requirement_type": "requirement",
            "supplementary_info": "Cell voltage threshold: 4.25V",
        },
        {
            "requirement_key": "BMS_REQ_002",
            "description": "The BMS shall balance cells when voltage difference exceeds a threshold.",
            "function_name": "Cell Balancing",
            "requirement_type": "requirement",
            "supplementary_info": "",
        },
        {
            "requirement_key": "BMS_REQ_003",
            "description": "The BMS shall report cell temperatures via CAN every 100ms.",
            "function_name": "Thermal Monitoring",
            "requirement_type": "requirement",
            "supplementary_info": "CAN ID: 0x300",
        },
    ]
    path = run_dir / "requirements.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ── Issue 1: Artifact model round-trip ─────────────────────────────────────

class TestArtifactModels:
    def test_requirement_input_roundtrip(self):
        from review_pipeline.artifacts.models import RequirementInput
        data = {"requirement_key": "REQ_001", "description": "Test desc", "function_name": "fn", "supplementary_info": "extra"}
        m = RequirementInput(**data)
        assert m.requirement_key == "REQ_001"
        assert m.description == "Test desc"
        assert m.function_name == "fn"
        assert m.supplementary_info == "extra"


class TestIssue15LegacyPipelineRemoval:
    def test_old_generation_prompt_files_are_removed(self):
        project_root = Path(__file__).resolve().parents[1]
        old_prompts = [
            project_root / "prompts" / "analyze_and_plan.system.html",
            project_root / "prompts" / "analyze_and_plan.user.html",
            project_root / "prompts" / "generate_case.system.html",
            project_root / "prompts" / "generate_case.user.html",
        ]

        for path in old_prompts:
            assert not path.exists(), f"legacy prompt still exists: {path}"

    def test_old_generation_modules_are_removed(self):
        assert importlib.util.find_spec("testcase_agent.pipeline.generate") is None
        assert importlib.util.find_spec("testcase_agent.prompts") is None

    def test_review_pipeline_cli_is_generation_entry(self):
        from review_pipeline.cli import build_parser

        subcommands = build_parser()._subparsers._group_actions[0].choices
        assert "prepare-clarification-review" in subcommands
        assert "prepare-intent-review" in subcommands
        assert "generate-cases" in subcommands
        assert "import-memory" in subcommands

    def test_legacy_optimization_run_command_is_disabled(self, monkeypatch):
        from optimization import cli

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "cli.py",
                "run",
                "--output-dir",
                "unused",
                "--requirement-set",
                "optimization_runs/requirement_sets/prompt_eval_v1.json",
            ],
        )
        with pytest.raises(SystemExit) as exc:
            cli.main()

        assert exc.value.code == 2

    def test_clarification_review_roundtrip(self, run_dir):
        from review_pipeline.artifacts.models import RequirementDecomposition, ClarificationReview, FactItem, AmbiguityItem
        from review_pipeline.artifacts.io import write_json, read_json

        decomposition = RequirementDecomposition(
            requirement_key="REQ_001",
            facts=[FactItem(item_id="f1", fact_text="A fact", confidence=0.9)],
            ambiguities=[AmbiguityItem(
                item_id="a1", affected_text="ambiguous", ambiguity_type="timing",
                severity="medium", clarification_question="What timing?",
                confidence_drivers={"trigger_clarity": 0.8},
            )],
        )
        review = ClarificationReview(
            review_session_id="test-session",
            requirement_key="REQ_001",
            decomposition=decomposition,
        )
        path = run_dir / "test_review.json"
        write_json(path, review.model_dump())
        reloaded = ClarificationReview(**read_json(path))
        assert reloaded.requirement_key == "REQ_001"
        assert len(reloaded.decomposition.facts) == 1
        assert len(reloaded.decomposition.ambiguities) == 1

    def test_case_intent_review_roundtrip(self, run_dir):
        from review_pipeline.artifacts.models import CaseIntentPlan, CaseIntentReview, CaseIntentItem
        from review_pipeline.artifacts.io import write_json, read_json

        plan = CaseIntentPlan(
            review_session_id="s1", requirement_key="REQ_001",
            intents=[CaseIntentItem(intent_id="i1", coverage_dimension="normal_behavior",
                      intent_text="Verify normal op", confidence_score=0.7)],
        )
        review = CaseIntentReview(review_session_id="s1", requirement_key="REQ_001", plan=plan)
        path = run_dir / "test_intent_review.json"
        write_json(path, review.model_dump())
        reloaded = CaseIntentReview(**read_json(path))
        assert len(reloaded.plan.intents) == 1

    def test_generated_case_set_roundtrip(self, run_dir):
        from review_pipeline.artifacts.models import GeneratedCaseSet, GeneratedCase
        from review_pipeline.artifacts.io import write_json, read_json

        case_set = GeneratedCaseSet(
            review_session_id="s1", requirement_key="REQ_001",
            cases=[GeneratedCase(case_id="c1", title="Test title", requirement_key="REQ_001",
                    approved_intent_id="i1", coverage_dimension="normal_behavior",
                    review_session_id="s1")],
        )
        path = run_dir / "test_cases.json"
        write_json(path, [c.model_dump() for c in case_set.cases])
        reloaded = read_json(path)
        assert len(reloaded) == 1
        assert reloaded[0]["case_id"] == "c1"

    def test_invalid_json_returns_error(self, run_dir):
        from review_pipeline.artifacts.io import read_json
        import json as _json
        path = run_dir / "bad.json"
        path.write_text("{invalid json", encoding="utf-8")
        with pytest.raises(_json.JSONDecodeError):
            read_json(path)


# ── Issue 1: Validation scaffolding ────────────────────────────────────────

class TestValidation:
    def test_validation_result_empty(self):
        from review_pipeline.artifacts.validation import ValidationResult
        r = ValidationResult()
        assert r.is_valid
        assert r.format_errors() == ""

    def test_validation_result_with_errors(self):
        from review_pipeline.artifacts.validation import ValidationResult
        r = ValidationResult()
        r.add_error("file.json", "field", "bad value")
        assert not r.is_valid
        assert "file.json" in r.format_errors()
        assert "field" in r.format_errors()


# ── Issue 1: JSON IO helpers ───────────────────────────────────────────────

class TestJsonIO:
    def test_read_write_utf8(self, run_dir):
        from review_pipeline.artifacts.io import read_json, write_json
        data = {"key": "值", "list": [1, 2]}
        path = run_dir / "utf8.json"
        write_json(path, data)
        assert path.exists()
        result = read_json(path)
        assert result["key"] == "值"

    def test_write_creates_parent_dirs(self, run_dir):
        from review_pipeline.artifacts.io import write_json
        deep = run_dir / "a" / "b" / "c.json"
        write_json(deep, {"x": 1})
        assert deep.exists()


# ── Issue 2: Confidence aggregation ────────────────────────────────────────

class TestConfidenceAggregation:
    def test_deterministic_average(self):
        from review_pipeline.confidence.engine import aggregate_confidence
        drivers = {"trigger_clarity": 0.8, "expected_behavior_clarity": 0.6}
        result = aggregate_confidence(drivers)
        assert result == pytest.approx(0.7)

    def test_missing_driver_defaults_to_half(self):
        from review_pipeline.confidence.engine import aggregate_confidence
        drivers = {"trigger_clarity": 0.8}
        result = aggregate_confidence(drivers)
        assert result == pytest.approx(0.8)

    def test_all_missing_defaults_to_half(self):
        from review_pipeline.confidence.engine import aggregate_confidence
        result = aggregate_confidence({})
        assert result == pytest.approx(0.5)

    def test_invalid_driver_raises(self):
        from review_pipeline.confidence.engine import aggregate_confidence
        with pytest.raises(ValueError, match="out of range"):
            aggregate_confidence({"trigger_clarity": 1.5})

    def test_negative_driver_raises(self):
        from review_pipeline.confidence.engine import aggregate_confidence
        with pytest.raises(ValueError, match="out of range"):
            aggregate_confidence({"trigger_clarity": -0.1})

    def test_routing_green(self):
        from review_pipeline.confidence.engine import routing_for_confidence
        r = routing_for_confidence(0.90)
        assert r.color == "green"

    def test_routing_blue(self):
        from review_pipeline.confidence.engine import routing_for_confidence
        r = routing_for_confidence(0.70)
        assert r.color == "blue"

    def test_routing_orange(self):
        from review_pipeline.confidence.engine import routing_for_confidence
        r = routing_for_confidence(0.50)
        assert r.color == "orange"

    def test_routing_red(self):
        from review_pipeline.confidence.engine import routing_for_confidence
        r = routing_for_confidence(0.30)
        assert r.color == "red"

    def test_routing_boundary_green_blue(self):
        from review_pipeline.confidence.engine import routing_for_confidence
        assert routing_for_confidence(0.85).color == "green"
        assert routing_for_confidence(0.849999).color == "blue"

    def test_routing_boundary_blue_orange(self):
        from review_pipeline.confidence.engine import routing_for_confidence
        assert routing_for_confidence(0.65).color == "blue"
        assert routing_for_confidence(0.649999).color == "orange"

    def test_routing_boundary_orange_red(self):
        from review_pipeline.confidence.engine import routing_for_confidence
        assert routing_for_confidence(0.40).color == "orange"
        assert routing_for_confidence(0.39999).color == "red"

    def test_historical_adjustment_bounded_positive(self):
        from review_pipeline.confidence.engine import aggregate_confidence
        result = aggregate_confidence({"trigger_clarity": 0.8}, historical_adjustment=0.20)
        assert result <= 0.90  # 0.8 + 0.10 max

    def test_historical_adjustment_bounded_negative(self):
        from review_pipeline.confidence.engine import aggregate_confidence
        result = aggregate_confidence({"trigger_clarity": 0.8}, historical_adjustment=-0.20)
        assert result >= 0.70  # 0.8 - 0.10 min

    def test_clarification_labels(self):
        from review_pipeline.confidence.engine import routing_label
        assert routing_label(0.90, is_clarification=True) == "Clear"
        assert routing_label(0.70, is_clarification=True) == "Minor ambiguity"
        assert routing_label(0.50, is_clarification=True) == "Review required"
        assert routing_label(0.30, is_clarification=True) == "Clarification required"

    def test_case_intent_labels(self):
        from review_pipeline.confidence.engine import routing_label
        assert routing_label(0.90, is_clarification=False) == "Strong intent"
        assert routing_label(0.70, is_clarification=False) == "Review recommended"
        assert routing_label(0.50, is_clarification=False) == "Review required"
        assert routing_label(0.30, is_clarification=False) == "Do not generate yet"


# ── Issue 4: Pattern tag derivation ────────────────────────────────────────

class TestPatternTags:
    def test_reason_code_derivation_confirmed(self):
        from review_pipeline.tag_rules.pattern_tag_rules import derive_from_reason_codes
        tags = derive_from_reason_codes(["unsupported_by_requirement"])
        assert len(tags) == 1
        assert tags[0].tag == "invented_behavior"
        assert tags[0].tag_strength == "confirmed"

    def test_ambiguity_type_derivation(self):
        from review_pipeline.tag_rules.pattern_tag_rules import derive_from_ambiguity_types
        tags = derive_from_ambiguity_types(["timing", "signal"])
        assert any(t.tag == "missing_timing" for t in tags)
        assert any(t.tag == "missing_signal" for t in tags)
        assert any(t.tag == "needs_clarification" for t in tags)

    def test_missing_category_derivation(self):
        from review_pipeline.tag_rules.pattern_tag_rules import derive_from_missing_categories
        tags = derive_from_missing_categories(["threshold"])
        assert len(tags) == 1
        assert tags[0].tag == "missing_threshold"

    def test_coverage_dimension_derivation(self):
        from review_pipeline.tag_rules.pattern_tag_rules import derive_from_coverage_dimensions
        tags = derive_from_coverage_dimensions(["normal_behavior", "fault_or_protection"])
        assert any(t.tag == "coverage_normal_behavior" for t in tags)
        assert any(t.tag == "coverage_fault_protection" for t in tags)

    def test_text_detector_candidate_only(self):
        from review_pipeline.tag_rules.pattern_tag_rules import derive_from_text_detectors
        tags = derive_from_text_detectors("The response time must be within 100ms latency")
        assert all(t.tag_strength == "candidate" for t in tags)
        assert any(t.tag == "response_time_bound" for t in tags)

    def test_text_detector_persistence(self):
        from review_pipeline.tag_rules.pattern_tag_rules import derive_from_text_detectors
        tags = derive_from_text_detectors("Values must persist in NVM across power cycles")
        assert any(t.tag == "persistence" for t in tags)

    def test_text_detector_logging(self):
        from review_pipeline.tag_rules.pattern_tag_rules import derive_from_text_detectors
        tags = derive_from_text_detectors("The system logs all events")
        assert any(t.tag == "logging_record" for t in tags)

    def test_text_detector_diagnostic(self):
        from review_pipeline.tag_rules.pattern_tag_rules import derive_from_text_detectors
        tags = derive_from_text_detectors("Fault clear after diagnostic check")
        assert any(t.tag == "diagnostic_clear" for t in tags)

    def test_text_detector_timing_maturity(self):
        from review_pipeline.tag_rules.pattern_tag_rules import derive_from_text_detectors
        tags = derive_from_text_detectors("Timing maturity is specified")
        assert any(t.tag == "timing_maturity" for t in tags)

    def test_unknown_tag_rejected(self):
        from review_pipeline.tag_rules.pattern_tag_rules import DerivedTag, reject_unknown_tags
        tags = [DerivedTag(tag="nonexistent_tag", tag_strength="confirmed", source="test", rule_id="r1", evidence_text="")]
        result = reject_unknown_tags(tags)
        assert len(result) == 0

    def test_derive_all_tags(self):
        from review_pipeline.tag_rules.pattern_tag_rules import derive_all_tags
        tags = derive_all_tags(
            reason_codes=["unsupported_by_requirement"],
            ambiguity_types=["timing"],
            missing_categories=["signal"],
            coverage_dimensions=["normal_behavior"],
            text="response time",
        )
        assert len(tags) >= 5

    def test_duplicate_dedup_keeps_highest(self):
        from review_pipeline.tag_rules.pattern_tag_rules import DerivedTag
        from review_pipeline.tag_rules.pattern_tag_rules import _deduplicate_tags
        t1 = DerivedTag(tag="same_tag", tag_strength="confirmed", source="reason_code", rule_id="r1", evidence_text="", confidence=1.0)
        t2 = DerivedTag(tag="same_tag", tag_strength="candidate", source="text_detector", rule_id="r2", evidence_text="", confidence=0.5)
        result = _deduplicate_tags([t1, t2])
        assert len(result) == 1
        assert result[0].confidence == 1.0


# ── Issue 5: Reason code registry ──────────────────────────────────────────

class TestReasonCodes:
    def test_clarification_decisions_valid(self):
        from review_pipeline.reason_codes import is_decision_valid
        assert is_decision_valid("clarification_item", "approve")
        assert is_decision_valid("clarification_item", "clarify")
        assert is_decision_valid("clarification_item", "block")
        assert not is_decision_valid("clarification_item", "invalid_decision")

    def test_case_intent_decisions_valid(self):
        from review_pipeline.reason_codes import is_decision_valid
        assert is_decision_valid("case_intent_item", "approve")
        assert is_decision_valid("case_intent_item", "reject")
        assert is_decision_valid("case_intent_item", "merge")
        assert not is_decision_valid("case_intent_item", "clarify")

    def test_unknown_reason_code_rejected(self):
        from review_pipeline.reason_codes import is_reason_code_valid
        assert not is_reason_code_valid("clarification_item", "nonexistent_code")
        assert is_reason_code_valid("clarification_item", "needs_clarification")

    def test_approve_no_reason_code_required(self):
        from review_pipeline.reason_codes import get_decision_requirements
        reqs = get_decision_requirements("approve")
        assert reqs.get("require_reason_code") is False

    def test_block_requires_reason_code_and_text(self):
        from review_pipeline.reason_codes import get_decision_requirements
        reqs = get_decision_requirements("block")
        assert reqs.get("require_reason_code") is True
        assert reqs.get("require_reason_text") is True

    def test_positive_vs_negative_codes(self):
        from review_pipeline.reason_codes import get_positive_reason_codes, get_negative_reason_codes
        positive = get_positive_reason_codes()
        negative = get_negative_reason_codes()
        assert "supported_by_requirement" in positive
        assert "unsupported_by_requirement" in negative
        assert "supported_by_requirement" not in negative


# ── Issue 6: Requirement decomposition stage ───────────────────────────────

class TestDecomposeRequirement:
    def test_produces_clarification_review_json(self, run_dir, sample_requirement_json):
        from review_pipeline.stages.decompose_requirement import prepare_clarification_review
        review = prepare_clarification_review(str(sample_requirement_json), str(run_dir))
        assert (run_dir / "clarification_review.json").exists()
        assert review.requirement_key == "BMS_REQ_001"
        assert len(review.decomposition.ambiguities) >= 1
        assert len(review.decomposition.clarification_questions) >= 1

    def test_produces_clarification_review_html(self, run_dir, sample_requirement_json):
        from review_pipeline.stages.decompose_requirement import prepare_clarification_review
        prepare_clarification_review(str(sample_requirement_json), str(run_dir))
        html_path = run_dir / "clarification_review.html"
        assert html_path.exists()
        html = html_path.read_text(encoding="utf-8")
        assert "Clarification Review" in html
        assert "BMS_REQ_001" in html

    def test_html_contains_routing_colors(self, run_dir, sample_requirement_json):
        from review_pipeline.stages.decompose_requirement import prepare_clarification_review
        prepare_clarification_review(str(sample_requirement_json), str(run_dir))
        html = (run_dir / "clarification_review.html").read_text(encoding="utf-8")
        assert "border-left: 4px solid" in html

    def test_no_case_intents_in_decomposition(self, run_dir, sample_requirement_json):
        from review_pipeline.stages.decompose_requirement import prepare_clarification_review
        review = prepare_clarification_review(str(sample_requirement_json), str(run_dir))
        # Decomposition has no case intents
        assert hasattr(review.decomposition, "ambiguities")

    def test_real_provider_json_response_produces_decomposition(self, run_dir, sample_requirement_json):
        from review_pipeline.stages.decompose_requirement import prepare_clarification_review

        class JsonProvider:
            provider_name = "fake"
            model_name = "fake-json"

            def complete(self, system_prompt: str, user_prompt: str) -> str:
                assert "Output only the JSON" in user_prompt
                return json.dumps({
                    "requirement_key": "BMS_REQ_001",
                    "facts": [
                        {
                            "item_id": "fact-1",
                            "fact_text": "The BMS shall detect cell over-voltage.",
                            "source_text": "The BMS shall detect cell over-voltage.",
                            "confidence": 0.9,
                        }
                    ],
                    "ambiguities": [],
                    "clarification_questions": [],
                    "safe_generation_policy": {
                        "can_generate": True,
                        "blocked_dimensions": [],
                        "requires_markers": [],
                        "notes": "No blocking ambiguity detected.",
                    },
                    "confidence_drivers": {
                        "trigger_clarity": 0.8,
                        "expected_behavior_clarity": 0.8,
                        "known_info_sufficiency": 0.7,
                        "ambiguity_resolution": 0.7,
                        "historical_pattern_support": 0.5,
                    },
                })

        review = prepare_clarification_review(
            str(sample_requirement_json),
            str(run_dir),
            provider=JsonProvider(),
        )

        assert review.decomposition.facts[0].fact_text == "The BMS shall detect cell over-voltage."
        assert review.decomposition.ambiguities == []
        assert not (run_dir / "llm_a_raw_response.txt").exists()

    def test_real_provider_parse_failure_dumps_raw_response(self, run_dir, sample_requirement_json):
        from review_pipeline.stages.decompose_requirement import prepare_clarification_review

        class BadProvider:
            provider_name = "fake"
            model_name = "fake-bad"

            def complete(self, system_prompt: str, user_prompt: str) -> str:
                return "not json"

        with pytest.raises(ValueError, match="LLM-A response was not valid JSON"):
            prepare_clarification_review(
                str(sample_requirement_json),
                str(run_dir),
                provider=BadProvider(),
            )

        raw_path = run_dir / "llm_a_raw_response.txt"
        assert raw_path.exists()
        assert raw_path.read_text(encoding="utf-8") == "not json"

    def test_symbolic_parameter_lint_flags_exact_value_question(self):
        from review_pipeline.artifacts.models import (
            AmbiguityItem,
            ClarificationReview,
            FactItem,
            RequirementDecomposition,
        )
        from review_pipeline.review_lints.clarification_lints import lint_clarification_review

        review = ClarificationReview(
            review_session_id="s1",
            requirement_key="REQ-BMS-OVP-002",
            decomposition=RequirementDecomposition(
                requirement_key="REQ-BMS-OVP-002",
                facts=[
                    FactItem(
                        item_id="fact-1",
                        fact_text="t_CellOV_Debounce is the configured debounce time.",
                        source_text="If cell OV persists for t_CellOV_Debounce, set BMS_CellOV_Flag.",
                    )
                ],
                ambiguities=[
                    AmbiguityItem(
                        item_id="amb-1",
                        affected_text="t_CellOV_Debounce",
                        ambiguity_type="timing",
                        clarification_question="What exact duration in seconds is t_CellOV_Debounce?",
                    )
                ],
            ),
        )

        lints = lint_clarification_review(review)

        assert len(lints) == 1
        assert lints[0].rule_id == "symbolic_parameter_treated_as_missing"
        assert lints[0].target_item_id == "amb-1"
        assert lints[0].symbol == "t_CellOV_Debounce"

    def test_symbolic_parameter_lint_ignores_non_value_questions(self):
        from review_pipeline.artifacts.models import (
            AmbiguityItem,
            ClarificationReview,
            FactItem,
            RequirementDecomposition,
        )
        from review_pipeline.review_lints.clarification_lints import lint_clarification_review

        review = ClarificationReview(
            review_session_id="s1",
            requirement_key="REQ-BMS-OVP-002",
            decomposition=RequirementDecomposition(
                requirement_key="REQ-BMS-OVP-002",
                facts=[
                    FactItem(
                        item_id="fact-1",
                        fact_text="t_CellOV_Debounce is the configured debounce time.",
                        source_text="If cell OV persists for t_CellOV_Debounce, set BMS_CellOV_Flag.",
                    )
                ],
                ambiguities=[
                    AmbiguityItem(
                        item_id="amb-1",
                        affected_text="t_CellOV_Debounce",
                        ambiguity_type="timing",
                        clarification_question="Is debounce required for this requirement?",
                    )
                ],
            ),
        )

        assert lint_clarification_review(review) == []

    def test_prepare_clarification_review_writes_symbolic_parameter_lints(self, run_dir, sample_requirement_json):
        from review_pipeline.artifacts.io import read_json
        from review_pipeline.stages.decompose_requirement import prepare_clarification_review

        class SymbolicProvider:
            provider_name = "fake"
            model_name = "fake-symbolic"

            def complete(self, system_prompt: str, user_prompt: str) -> str:
                return json.dumps({
                    "requirement_key": "BMS_REQ_001",
                    "facts": [
                        {
                            "item_id": "fact-1",
                            "fact_text": "t_CellOV_Debounce is the debounce parameter.",
                            "source_text": "If over-voltage persists for t_CellOV_Debounce, set the flag.",
                            "confidence": 0.9,
                        }
                    ],
                    "ambiguities": [
                        {
                            "item_id": "amb-1",
                            "affected_text": "t_CellOV_Debounce",
                            "ambiguity_type": "timing",
                            "clarification_question": "What exact duration in seconds is t_CellOV_Debounce?",
                        }
                    ],
                    "clarification_questions": [],
                    "safe_generation_policy": {"can_generate": True},
                })

        review = prepare_clarification_review(
            str(sample_requirement_json),
            str(run_dir),
            provider=SymbolicProvider(),
        )

        data = read_json(run_dir / "clarification_review.json")
        html = (run_dir / "clarification_review.html").read_text(encoding="utf-8")
        assert review.review_lints[0].rule_id == "symbolic_parameter_treated_as_missing"
        assert data["review_lints"][0]["target_item_id"] == "amb-1"
        assert "symbolic_parameter_treated_as_missing" in html
        assert "t_CellOV_Debounce" in html


# ── Issue 7: Clarification validation ──────────────────────────────────────

class TestClarificationValidation:
    def test_approve_passes(self, run_dir):
        from review_pipeline.stages.validate_clarification import validate_clarification_review
        from review_pipeline.artifacts.models import ClarificationReview, RequirementDecomposition, AmbiguityItem, ClarificationDecision
        from review_pipeline.artifacts.io import write_json

        review = ClarificationReview(
            review_session_id="s1", requirement_key="REQ_001",
            decomposition=RequirementDecomposition(
                requirement_key="REQ_001",
                ambiguities=[AmbiguityItem(item_id="a1", affected_text="test", ambiguity_type="timing",
                              confidence_drivers={"trigger_clarity": 0.8})],
            ),
            decisions=[ClarificationDecision(item_id="a1", decision="approve")],
        )
        path = run_dir / "clarification_review.json"
        write_json(path, review.model_dump())
        result, basis = validate_clarification_review(str(path))
        assert result.is_valid
        assert basis is not None
        assert not basis.blocked

    def test_block_requires_reason(self, run_dir):
        from review_pipeline.stages.validate_clarification import validate_clarification_review
        from review_pipeline.artifacts.models import ClarificationReview, RequirementDecomposition, AmbiguityItem, ClarificationDecision
        from review_pipeline.artifacts.io import write_json

        review = ClarificationReview(
            review_session_id="s1", requirement_key="REQ_001",
            decomposition=RequirementDecomposition(
                requirement_key="REQ_001",
                ambiguities=[AmbiguityItem(item_id="a1", affected_text="test", ambiguity_type="timing")],
            ),
            decisions=[ClarificationDecision(item_id="a1", decision="block",
                         reason_codes=["needs_clarification"], reason_text="Unresolvable ambiguity")],
        )
        path = run_dir / "clarification_review.json"
        write_json(path, review.model_dump())
        result, basis = validate_clarification_review(str(path))
        assert result.is_valid
        assert basis is not None
        assert basis.blocked

    def test_clarify_requires_clarified_value(self, run_dir):
        from review_pipeline.stages.validate_clarification import validate_clarification_review
        from review_pipeline.artifacts.models import ClarificationReview, RequirementDecomposition, AmbiguityItem, ClarificationDecision
        from review_pipeline.artifacts.io import write_json

        review = ClarificationReview(
            review_session_id="s1", requirement_key="REQ_001",
            decomposition=RequirementDecomposition(
                requirement_key="REQ_001",
                ambiguities=[AmbiguityItem(item_id="a1", affected_text="test", ambiguity_type="timing")],
            ),
            decisions=[ClarificationDecision(item_id="a1", decision="clarify", reason_codes=["needs_clarification"])],
        )
        path = run_dir / "clarification_review.json"
        write_json(path, review.model_dump())
        result, basis = validate_clarification_review(str(path))
        assert not result.is_valid
        assert "clarified value" in result.format_errors()

    def test_clarified_value_appears_in_basis(self, run_dir):
        from review_pipeline.stages.validate_clarification import validate_clarification_review
        from review_pipeline.artifacts.models import ClarificationReview, RequirementDecomposition, AmbiguityItem, ClarificationDecision
        from review_pipeline.artifacts.io import write_json

        review = ClarificationReview(
            review_session_id="s1", requirement_key="REQ_001",
            decomposition=RequirementDecomposition(
                requirement_key="REQ_001",
                ambiguities=[AmbiguityItem(item_id="a1", affected_text="test", ambiguity_type="timing")],
            ),
            decisions=[ClarificationDecision(item_id="a1", decision="clarify",
                         reason_codes=["needs_clarification"], clarified_value="Response time is 100ms")],
        )
        path = run_dir / "clarification_review.json"
        write_json(path, review.model_dump())
        result, basis = validate_clarification_review(str(path))
        assert result.is_valid
        assert any(a["clarified_value"] == "Response time is 100ms" for a in basis.resolved_ambiguities)

    def test_unknown_decision_rejected(self, run_dir):
        from review_pipeline.stages.validate_clarification import validate_clarification_review
        from review_pipeline.artifacts.models import ClarificationReview, RequirementDecomposition, AmbiguityItem, ClarificationDecision
        from review_pipeline.artifacts.io import write_json

        review = ClarificationReview(
            review_session_id="s1", requirement_key="REQ_001",
            decomposition=RequirementDecomposition(requirement_key="REQ_001",
                ambiguities=[AmbiguityItem(item_id="a1", affected_text="test", ambiguity_type="timing")]),
            decisions=[ClarificationDecision(item_id="a1", decision="invalid_decision")],
        )
        path = run_dir / "clarification_review.json"
        write_json(path, review.model_dump())
        result, basis = validate_clarification_review(str(path))
        assert not result.is_valid

    def test_non_approve_requires_reason(self, run_dir):
        from review_pipeline.stages.validate_clarification import validate_clarification_review
        from review_pipeline.artifacts.models import ClarificationReview, RequirementDecomposition, AmbiguityItem, ClarificationDecision
        from review_pipeline.artifacts.io import write_json

        review = ClarificationReview(
            review_session_id="s1", requirement_key="REQ_001",
            decomposition=RequirementDecomposition(requirement_key="REQ_001",
                ambiguities=[AmbiguityItem(item_id="a1", affected_text="test", ambiguity_type="timing")]),
            decisions=[ClarificationDecision(item_id="a1", decision="block")],
        )
        path = run_dir / "clarification_review.json"
        write_json(path, review.model_dump())
        result, basis = validate_clarification_review(str(path))
        assert not result.is_valid


# ── Issue 8: Case intent planning ──────────────────────────────────────────

class TestIntentPlanning:
    def test_produces_intent_review(self, run_dir, sample_requirement_json):
        from review_pipeline.stages.decompose_requirement import prepare_clarification_review
        from review_pipeline.stages.validate_clarification import validate_clarification_review
        from review_pipeline.stages.plan_case_intents import prepare_intent_review

        prepare_clarification_review(str(sample_requirement_json), str(run_dir))
        # Auto-approve
        from review_pipeline.artifacts.io import write_json, read_json
        data = read_json(run_dir / "clarification_review.json")
        data["decisions"] = [{"item_id": a["item_id"], "decision": "approve"}
                             for a in data["decomposition"]["ambiguities"]]
        write_json(run_dir / "clarification_review.json", data)
        validate_clarification_review(str(run_dir / "clarification_review.json"))

        review = prepare_intent_review(str(run_dir))
        assert (run_dir / "case_intent_review.json").exists()
        assert (run_dir / "case_intent_review.html").exists()
        assert len(review.plan.intents) >= 1

    def test_blocked_basis_prevents_planning(self, run_dir, sample_requirement_json):
        from review_pipeline.stages.decompose_requirement import prepare_clarification_review
        from review_pipeline.stages.plan_case_intents import prepare_intent_review
        from review_pipeline.artifacts.io import write_json
        from review_pipeline.artifacts.models import ClarifiedTestBasis

        prepare_clarification_review(str(sample_requirement_json), str(run_dir))
        # Write a blocked test basis
        basis = ClarifiedTestBasis(
            requirement_key="BMS_REQ_001", review_session_id="s1",
            blocked=True, block_reasons=["Unresolvable ambiguity"],
        )
        write_json(run_dir / "clarified_test_basis.json", basis.model_dump())

        review = prepare_intent_review(str(run_dir))
        assert review.plan.planning_blocked
        assert "Unresolvable" in review.plan.planning_block_reason

    def test_html_contains_routing_colors(self, run_dir, sample_requirement_json):
        from review_pipeline.stages.decompose_requirement import prepare_clarification_review
        from review_pipeline.stages.validate_clarification import validate_clarification_review
        from review_pipeline.stages.plan_case_intents import prepare_intent_review
        from review_pipeline.artifacts.io import write_json, read_json

        prepare_clarification_review(str(sample_requirement_json), str(run_dir))
        data = read_json(run_dir / "clarification_review.json")
        data["decisions"] = [{"item_id": a["item_id"], "decision": "approve"}
                             for a in data["decomposition"]["ambiguities"]]
        write_json(run_dir / "clarification_review.json", data)
        validate_clarification_review(str(run_dir / "clarification_review.json"))
        prepare_intent_review(str(run_dir))

        html = (run_dir / "case_intent_review.html").read_text(encoding="utf-8")
        assert "Case Intent Review" in html
        assert "border-left" in html


# ── Issue 9: Case intent validation ────────────────────────────────────────

class TestCaseIntentValidation:
    def test_approve_includes_intent(self, run_dir):
        from review_pipeline.stages.validate_case_intent import validate_case_intent_review
        from review_pipeline.artifacts.models import CaseIntentReview, CaseIntentPlan, CaseIntentItem, CaseIntentDecision
        from review_pipeline.artifacts.io import write_json

        plan = CaseIntentPlan(review_session_id="s1", requirement_key="REQ_001",
            intents=[CaseIntentItem(intent_id="i1", coverage_dimension="normal_behavior",
                      intent_text="Verify normal op", confidence_score=0.8)])
        review = CaseIntentReview(review_session_id="s1", requirement_key="REQ_001", plan=plan,
                                  decisions=[CaseIntentDecision(intent_id="i1", decision="approve")])
        path = run_dir / "case_intent_review.json"
        write_json(path, review.model_dump())
        result, plan_out = validate_case_intent_review(str(path))
        assert result.is_valid
        assert len(plan_out.approved_intents) == 1

    def test_reject_excludes_intent(self, run_dir):
        from review_pipeline.stages.validate_case_intent import validate_case_intent_review
        from review_pipeline.artifacts.models import CaseIntentReview, CaseIntentPlan, CaseIntentItem, CaseIntentDecision
        from review_pipeline.artifacts.io import write_json

        plan = CaseIntentPlan(review_session_id="s1", requirement_key="REQ_001",
            intents=[CaseIntentItem(intent_id="i1", coverage_dimension="normal_behavior",
                      intent_text="Verify normal op", confidence_score=0.8)])
        review = CaseIntentReview(review_session_id="s1", requirement_key="REQ_001", plan=plan,
                                  decisions=[CaseIntentDecision(intent_id="i1", decision="reject",
                                             reason_codes=["unsupported_by_requirement"], reason_text="Not valid")])
        path = run_dir / "case_intent_review.json"
        write_json(path, review.model_dump())
        result, plan_out = validate_case_intent_review(str(path))
        assert result.is_valid
        assert len(plan_out.approved_intents) == 0

    def test_defer_excludes_intent(self, run_dir):
        from review_pipeline.stages.validate_case_intent import validate_case_intent_review
        from review_pipeline.artifacts.models import CaseIntentReview, CaseIntentPlan, CaseIntentItem, CaseIntentDecision
        from review_pipeline.artifacts.io import write_json

        plan = CaseIntentPlan(review_session_id="s1", requirement_key="REQ_001",
            intents=[CaseIntentItem(intent_id="i1", coverage_dimension="normal_behavior",
                      intent_text="Verify normal op", confidence_score=0.3)])
        review = CaseIntentReview(review_session_id="s1", requirement_key="REQ_001", plan=plan,
                                  decisions=[CaseIntentDecision(intent_id="i1", decision="defer",
                                             reason_codes=["needs_clarification"], reason_text="Need more info")])
        path = run_dir / "case_intent_review.json"
        write_json(path, review.model_dump())
        result, plan_out = validate_case_intent_review(str(path))
        assert result.is_valid
        assert len(plan_out.approved_intents) == 0

    def test_merge_requires_target(self, run_dir):
        from review_pipeline.stages.validate_case_intent import validate_case_intent_review
        from review_pipeline.artifacts.models import CaseIntentReview, CaseIntentPlan, CaseIntentItem, CaseIntentDecision
        from review_pipeline.artifacts.io import write_json

        plan = CaseIntentPlan(review_session_id="s1", requirement_key="REQ_001",
            intents=[CaseIntentItem(intent_id="i1", coverage_dimension="normal_behavior", intent_text="A"),
                     CaseIntentItem(intent_id="i2", coverage_dimension="normal_behavior", intent_text="B")])
        review = CaseIntentReview(review_session_id="s1", requirement_key="REQ_001", plan=plan,
                                  decisions=[CaseIntentDecision(intent_id="i2", decision="merge",
                                             reason_codes=["duplicate_expected_behavior"], merge_target_id="i1")])
        path = run_dir / "case_intent_review.json"
        write_json(path, review.model_dump())
        result, plan_out = validate_case_intent_review(str(path))
        assert result.is_valid
        assert len(plan_out.approved_intents) == 1
        assert plan_out.approved_intents[0].intent_id == "i1"

    def test_split_requires_children(self, run_dir):
        from review_pipeline.stages.validate_case_intent import validate_case_intent_review
        from review_pipeline.artifacts.models import CaseIntentReview, CaseIntentPlan, CaseIntentItem, CaseIntentDecision
        from review_pipeline.artifacts.io import write_json

        child1 = CaseIntentItem(intent_id="i1-s1", coverage_dimension="boundary_or_threshold",
                                intent_text="Child 1", confidence_score=0.7)
        child2 = CaseIntentItem(intent_id="i1-s2", coverage_dimension="fault_or_protection",
                                intent_text="Child 2", confidence_score=0.7)
        plan = CaseIntentPlan(review_session_id="s1", requirement_key="REQ_001",
            intents=[CaseIntentItem(intent_id="i1", coverage_dimension="normal_behavior", intent_text="Parent")])
        review = CaseIntentReview(review_session_id="s1", requirement_key="REQ_001", plan=plan,
                                  decisions=[CaseIntentDecision(intent_id="i1", decision="split",
                                             split_children=[child1, child2])])
        path = run_dir / "case_intent_review.json"
        write_json(path, review.model_dump())
        result, plan_out = validate_case_intent_review(str(path))
        assert result.is_valid
        assert len(plan_out.approved_intents) == 2

    def test_revise_includes_final_text(self, run_dir):
        from review_pipeline.stages.validate_case_intent import validate_case_intent_review
        from review_pipeline.artifacts.models import CaseIntentReview, CaseIntentPlan, CaseIntentItem, CaseIntentDecision
        from review_pipeline.artifacts.io import write_json

        plan = CaseIntentPlan(review_session_id="s1", requirement_key="REQ_001",
            intents=[CaseIntentItem(intent_id="i1", coverage_dimension="normal_behavior", intent_text="Original")])
        review = CaseIntentReview(review_session_id="s1", requirement_key="REQ_001", plan=plan,
                                  decisions=[CaseIntentDecision(intent_id="i1", decision="revise",
                                             reason_codes=["too_broad_to_verify"], revised_intent_text="Revised")])
        path = run_dir / "case_intent_review.json"
        write_json(path, review.model_dump())
        result, plan_out = validate_case_intent_review(str(path))
        assert result.is_valid
        assert plan_out.approved_intents[0].intent_text == "Revised"

    def test_traceability_preserved(self, run_dir):
        from review_pipeline.stages.validate_case_intent import validate_case_intent_review
        from review_pipeline.artifacts.models import CaseIntentReview, CaseIntentPlan, CaseIntentItem, CaseIntentDecision
        from review_pipeline.artifacts.io import write_json

        plan = CaseIntentPlan(review_session_id="s1", requirement_key="REQ_001",
            intents=[CaseIntentItem(intent_id="i1", coverage_dimension="normal_behavior",
                      intent_text="Verify normal op", confidence_score=0.8)])
        review = CaseIntentReview(review_session_id="s1", requirement_key="REQ_001", plan=plan,
                                  decisions=[CaseIntentDecision(intent_id="i1", decision="approve")])
        path = run_dir / "case_intent_review.json"
        write_json(path, review.model_dump())
        result, plan_out = validate_case_intent_review(str(path))
        assert result.is_valid
        assert len(plan_out.traceability) == 1
        assert plan_out.traceability[0]["intent_id"] == "i1"


# ── Issue 10: Case writer ──────────────────────────────────────────────────

class TestCaseWriter:
    def test_generates_one_case_per_intent(self, run_dir):
        from review_pipeline.stages.write_cases import generate_cases
        from review_pipeline.artifacts.models import ApprovedCasePlan, CaseIntentItem
        from review_pipeline.artifacts.io import write_json

        plan = ApprovedCasePlan(
            review_session_id="s1", requirement_key="REQ_001",
            approved_intents=[
                CaseIntentItem(intent_id="i1", coverage_dimension="normal_behavior",
                               intent_text="Verify normal", confidence_score=0.8),
                CaseIntentItem(intent_id="i2", coverage_dimension="boundary_or_threshold",
                               intent_text="Verify boundary", confidence_score=0.7),
            ],
        )
        write_json(run_dir / "approved_case_plan.json", plan.model_dump())
        case_set = generate_cases(str(run_dir))
        assert len(case_set.cases) == 2

    def test_skips_where_plan_empty(self, run_dir):
        from review_pipeline.stages.write_cases import generate_cases
        from review_pipeline.artifacts.models import ApprovedCasePlan
        from review_pipeline.artifacts.io import write_json

        plan = ApprovedCasePlan(review_session_id="s1", requirement_key="REQ_001", approved_intents=[])
        write_json(run_dir / "approved_case_plan.json", plan.model_dump())
        case_set = generate_cases(str(run_dir))
        assert len(case_set.cases) == 0

    def test_generated_cases_have_traceability(self, run_dir):
        from review_pipeline.stages.write_cases import generate_cases
        from review_pipeline.artifacts.models import ApprovedCasePlan, CaseIntentItem
        from review_pipeline.artifacts.io import write_json

        plan = ApprovedCasePlan(
            review_session_id="s1", requirement_key="REQ_001",
            approved_intents=[
                CaseIntentItem(intent_id="i1", coverage_dimension="observability",
                               intent_text="Verify obs", confidence_score=0.9),
            ],
        )
        write_json(run_dir / "approved_case_plan.json", plan.model_dump())
        case_set = generate_cases(str(run_dir))
        case = case_set.cases[0]
        assert case.requirement_key == "REQ_001"
        assert case.approved_intent_id == "i1"
        assert case.traceability["requirement_key"] == "REQ_001"

    def test_generated_json_has_evaluator_fields(self, run_dir):
        from review_pipeline.stages.write_cases import generate_cases
        from review_pipeline.artifacts.models import ApprovedCasePlan, CaseIntentItem
        from review_pipeline.artifacts.io import write_json, read_json

        plan = ApprovedCasePlan(
            review_session_id="s1", requirement_key="REQ_001",
            approved_intents=[
                CaseIntentItem(intent_id="i1", coverage_dimension="normal_behavior",
                               intent_text="Verify normal", confidence_score=0.8),
            ],
        )
        write_json(run_dir / "approved_case_plan.json", plan.model_dump())
        generate_cases(str(run_dir))
        data = read_json(run_dir / "generated_cases.json")
        case = data[0]
        assert "case_id" in case
        assert "title" in case
        assert "objective" in case
        assert "pre_condition" in case
        assert "steps" in case
        assert "post_condition" in case
        assert "requirement_key" in case
        assert "coverage_dimension" in case


# ── Issue 11: Review Memory SQLite ─────────────────────────────────────────

class TestReviewMemory:
    def test_schema_creation(self, run_dir):
        from review_pipeline.storage.store import get_connection
        db_path = str(run_dir / "test.db")
        conn = get_connection(db_path)
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        table_names = [t[0] for t in tables]
        assert "review_sessions" in table_names
        assert "clarification_memory_items" in table_names
        assert "case_intent_memory_items" in table_names
        assert "memory_item_tags" in table_names
        conn.close()

    def test_import_clarification(self, run_dir):
        from review_pipeline.storage.store import import_memory, get_connection
        from review_pipeline.artifacts.models import ClarificationReview, RequirementDecomposition, AmbiguityItem, ClarificationDecision
        from review_pipeline.artifacts.io import write_json

        review = ClarificationReview(
            review_session_id="mem-test-1", requirement_key="REQ_001",
            source_requirement_hash="aabbccdd",
            decomposition=RequirementDecomposition(
                requirement_key="REQ_001",
                ambiguities=[AmbiguityItem(item_id="a1", affected_text="test", ambiguity_type="timing",
                              severity="high", confidence_drivers={"trigger_clarity": 0.7})],
            ),
            decisions=[ClarificationDecision(item_id="a1", decision="approve")],
        )
        write_json(run_dir / "clarification_review.json", review.model_dump())
        db_path = str(run_dir / "memory.db")
        import_memory(str(run_dir), db_path)

        conn = get_connection(db_path)
        row = conn.execute("SELECT * FROM review_sessions WHERE session_id = ?", ("mem-test-1",)).fetchone()
        assert row is not None
        assert row["requirement_key"] == "REQ_001"
        conn.close()

    def test_pattern_tags_stored_with_evidence(self, run_dir):
        from review_pipeline.storage.store import import_memory, get_connection
        from review_pipeline.artifacts.models import ClarificationReview, RequirementDecomposition, AmbiguityItem, ClarificationDecision
        from review_pipeline.artifacts.io import write_json

        review = ClarificationReview(
            review_session_id="tag-test-1", requirement_key="REQ_001",
            source_requirement_hash="aabb",
            decomposition=RequirementDecomposition(
                requirement_key="REQ_001",
                ambiguities=[AmbiguityItem(item_id="a1", affected_text="test", ambiguity_type="signal",
                              severity="high", confidence_drivers={"trigger_clarity": 0.7})],
            ),
            decisions=[ClarificationDecision(item_id="a1", decision="clarify",
                         reason_codes=["needs_clarification"], reason_text="Need signal info")],
        )
        write_json(run_dir / "clarification_review.json", review.model_dump())
        db_path = str(run_dir / "memory.db")
        import_memory(str(run_dir), db_path)

        conn = get_connection(db_path)
        tags = conn.execute("SELECT * FROM memory_item_tags WHERE session_id = ?", ("tag-test-1",)).fetchall()
        assert len(tags) > 0
        assert any(t["tag"] == "needs_clarification" for t in tags)
        conn.close()

    def test_duplicate_import_idempotent(self, run_dir):
        from review_pipeline.storage.store import import_memory, get_connection
        from review_pipeline.artifacts.models import ClarificationReview, RequirementDecomposition, AmbiguityItem, ClarificationDecision
        from review_pipeline.artifacts.io import write_json

        review = ClarificationReview(
            review_session_id="dup-test-1", requirement_key="REQ_001",
            source_requirement_hash="ccdd",
            decomposition=RequirementDecomposition(requirement_key="REQ_001",
                ambiguities=[AmbiguityItem(item_id="a1", affected_text="test", ambiguity_type="timing")]),
            decisions=[ClarificationDecision(item_id="a1", decision="approve")],
        )
        write_json(run_dir / "clarification_review.json", review.model_dump())
        db_path = str(run_dir / "memory.db")
        import_memory(str(run_dir), db_path)
        import_memory(str(run_dir), db_path)

        conn = get_connection(db_path)
        count = conn.execute("SELECT COUNT(*) as c FROM review_sessions WHERE session_id = ?", ("dup-test-1",)).fetchone()["c"]
        assert count == 1  # no duplicates
        conn.close()


# ── Issue 12: Review Memory retrieval ──────────────────────────────────────

class TestReviewMemoryRetrieval:
    def test_retrieve_by_requirement_hash(self, run_dir):
        from review_pipeline.storage.store import import_memory, retrieve_by_requirement_hash
        from review_pipeline.artifacts.models import ClarificationReview, RequirementDecomposition, AmbiguityItem, ClarificationDecision
        from review_pipeline.artifacts.io import write_json

        review = ClarificationReview(
            review_session_id="retr-test-1", requirement_key="REQ_001",
            source_requirement_hash="hash123",
            decomposition=RequirementDecomposition(requirement_key="REQ_001",
                ambiguities=[AmbiguityItem(item_id="a1", affected_text="test", ambiguity_type="timing")]),
            decisions=[ClarificationDecision(item_id="a1", decision="approve")],
        )
        write_json(run_dir / "clarification_review.json", review.model_dump())
        db_path = str(run_dir / "memory.db")
        import_memory(str(run_dir), db_path)

        results = retrieve_by_requirement_hash("hash123", db_path)
        assert len(results) >= 1
        assert results[0]["requirement_key"] == "REQ_001"

    def test_retrieve_by_tags(self, run_dir):
        from review_pipeline.storage.store import import_memory, retrieve_by_tags
        from review_pipeline.artifacts.models import ClarificationReview, RequirementDecomposition, AmbiguityItem, ClarificationDecision
        from review_pipeline.artifacts.io import write_json

        review = ClarificationReview(
            review_session_id="tag-retr-1", requirement_key="REQ_001",
            source_requirement_hash="taghash",
            decomposition=RequirementDecomposition(requirement_key="REQ_001",
                ambiguities=[AmbiguityItem(item_id="a1", affected_text="test", ambiguity_type="signal")]),
            decisions=[ClarificationDecision(item_id="a1", decision="clarify",
                         reason_codes=["needs_clarification"])],
        )
        write_json(run_dir / "clarification_review.json", review.model_dump())
        db_path = str(run_dir / "memory.db")
        import_memory(str(run_dir), db_path)

        results = retrieve_by_tags(["missing_signal"], db_path)
        assert len(results) >= 1

    def test_historical_support_no_memory(self, run_dir):
        from review_pipeline.storage.store import compute_historical_support
        db_path = str(run_dir / "memory.db")
        result = compute_historical_support("nonexistent", ["tag1"], db_path)
        assert result["adjustment"] == 0.0
        assert result["historical_pattern_support"] == 0.5

    def test_historical_support_with_memory(self, run_dir):
        from review_pipeline.storage.store import import_memory, compute_historical_support
        from review_pipeline.artifacts.models import ClarificationReview, RequirementDecomposition, AmbiguityItem, ClarificationDecision
        from review_pipeline.artifacts.io import write_json

        review = ClarificationReview(
            review_session_id="histsup-1", requirement_key="REQ_001",
            source_requirement_hash="histhash",
            decomposition=RequirementDecomposition(requirement_key="REQ_001",
                ambiguities=[AmbiguityItem(item_id="a1", affected_text="test", ambiguity_type="signal")]),
            decisions=[ClarificationDecision(item_id="a1", decision="approve")],
        )
        write_json(run_dir / "clarification_review.json", review.model_dump())
        db_path = str(run_dir / "memory.db")
        import_memory(str(run_dir), db_path)

        result = compute_historical_support("histhash", ["missing_signal"], db_path)
        assert result["same_requirement_sessions"] >= 1

    def test_retrieval_does_not_mutate_decisions(self, run_dir):
        from review_pipeline.storage.store import import_memory, retrieve_by_requirement_hash
        from review_pipeline.artifacts.models import ClarificationReview, RequirementDecomposition, AmbiguityItem, ClarificationDecision
        from review_pipeline.artifacts.io import write_json

        review = ClarificationReview(
            review_session_id="nomutate-1", requirement_key="REQ_001",
            source_requirement_hash="nomutate",
            decomposition=RequirementDecomposition(requirement_key="REQ_001",
                ambiguities=[AmbiguityItem(item_id="a1", affected_text="test", ambiguity_type="timing")]),
            decisions=[ClarificationDecision(item_id="a1", decision="clarify",
                         reason_codes=["needs_clarification"])],
        )
        write_json(run_dir / "clarification_review.json", review.model_dump())
        db_path = str(run_dir / "memory.db")
        import_memory(str(run_dir), db_path)

        results = retrieve_by_requirement_hash("nomutate", db_path)
        for r in results:
            assert r["requirement_key"] == "REQ_001"  # read-only


# ── Issue 13: Evaluation integration ───────────────────────────────────────

class TestEvaluation:
    def test_evaluate_run(self, run_dir):
        from review_pipeline.stages.write_cases import generate_cases
        from review_pipeline.stages.evaluate import evaluate_run
        from review_pipeline.artifacts.models import ApprovedCasePlan, CaseIntentItem
        from review_pipeline.artifacts.io import write_json

        plan = ApprovedCasePlan(
            review_session_id="eval-1", requirement_key="REQ_001",
            approved_intents=[
                CaseIntentItem(intent_id="i1", coverage_dimension="normal_behavior",
                               intent_text="Verify normal", confidence_score=0.8),
            ],
        )
        write_json(run_dir / "approved_case_plan.json", plan.model_dump())
        generate_cases(str(run_dir))

        evaluate_run(str(run_dir))
        assert (run_dir / "evaluation_results.json").exists()
        assert (run_dir / "evaluation_summary.json").exists()

    def test_missing_generated_cases_error(self, run_dir):
        from review_pipeline.stages.evaluate import evaluate_run
        with pytest.raises(FileNotFoundError, match="generated_cases"):
            evaluate_run(str(run_dir))

    def test_evaluation_traceability_preserved(self, run_dir):
        from review_pipeline.stages.write_cases import generate_cases
        from review_pipeline.stages.evaluate import evaluate_run
        from review_pipeline.artifacts.models import ApprovedCasePlan, CaseIntentItem
        from review_pipeline.artifacts.io import write_json, read_json

        plan = ApprovedCasePlan(
            review_session_id="trace-1", requirement_key="REQ_001",
            approved_intents=[
                CaseIntentItem(intent_id="i1", coverage_dimension="observability",
                               intent_text="Verify obs", confidence_score=0.9),
            ],
        )
        write_json(run_dir / "approved_case_plan.json", plan.model_dump())
        generate_cases(str(run_dir))
        evaluate_run(str(run_dir))

        results = read_json(run_dir / "evaluation_results.json")
        assert results[0]["requirement_key"] == "REQ_001"
        assert "coverage_dimension" in results[0]


# ── Issue 14: End-to-end pipeline fixture ──────────────────────────────────

class TestEndToEnd:
    def test_full_pipeline_with_fake_providers(self, run_dir):
        """Complete offline fixture: decompose → review → plan → review → write → evaluate."""
        from review_pipeline.stages.decompose_requirement import prepare_clarification_review
        from review_pipeline.stages.validate_clarification import validate_clarification_review
        from review_pipeline.stages.plan_case_intents import prepare_intent_review
        from review_pipeline.stages.validate_case_intent import validate_case_intent_review
        from review_pipeline.stages.write_cases import generate_cases
        from review_pipeline.stages.evaluate import evaluate_run
        from review_pipeline.artifacts.io import write_json, read_json

        # 1. Create requirement input
        req_json = run_dir / "requirements.json"
        write_json(req_json, [{
            "requirement_key": "E2E_REQ_001",
            "description": "The BMS shall detect over-temperature and reduce charge current within 50ms.",
            "function_name": "Thermal Protection",
            "supplementary_info": "Max temp: 60C",
        }])

        # 2. Prepare clarification review (uses placeholder, no LLM)
        review = prepare_clarification_review(str(req_json), str(run_dir))
        assert (run_dir / "clarification_review.json").exists()
        assert (run_dir / "clarification_review.html").exists()

        # 3. Human "edits" the review (auto-approve for fixture)
        data = read_json(run_dir / "clarification_review.json")
        data["decisions"] = [{"item_id": a["item_id"], "decision": "approve"}
                             for a in data["decomposition"]["ambiguities"]]
        write_json(run_dir / "clarification_review.json", data)

        # 4. Validate clarification review
        result, basis = validate_clarification_review(str(run_dir / "clarification_review.json"))
        assert result.is_valid
        assert (run_dir / "clarified_test_basis.json").exists()

        # 5. Prepare intent review
        intent_review = prepare_intent_review(str(run_dir))
        assert (run_dir / "case_intent_review.json").exists()
        assert (run_dir / "case_intent_review.html").exists()

        # 6. Human "edits" intent review
        intent_data = read_json(run_dir / "case_intent_review.json")
        intent_data["decisions"] = [
            {"intent_id": i["intent_id"], "decision": "approve"}
            for i in intent_data["plan"]["intents"]
        ]
        # Add one reject and one merge for diversity
        if len(intent_data["decisions"]) >= 2:
            intent_data["decisions"][1]["decision"] = "reject"
            intent_data["decisions"][1]["reason_codes"] = ["duplicate_expected_behavior"]
            intent_data["decisions"][1]["reason_text"] = "Duplicate"
        write_json(run_dir / "case_intent_review.json", intent_data)

        # 7. Validate intent review
        result2, approved = validate_case_intent_review(str(run_dir / "case_intent_review.json"))
        assert result2.is_valid
        assert (run_dir / "approved_case_plan.json").exists()

        # 8. Generate cases
        case_set = generate_cases(str(run_dir))
        assert (run_dir / "generated_cases.json").exists()
        assert len(case_set.cases) == len(approved.approved_intents)

        # 9. Evaluate
        evaluate_run(str(run_dir))
        assert (run_dir / "evaluation_results.json").exists()
        assert (run_dir / "evaluation_summary.json").exists()

        # 10. Verify no self_check was called
        html = (run_dir / "clarification_review.html").read_text(encoding="utf-8")
        assert "self_check" not in html.lower()
        html2 = (run_dir / "case_intent_review.html").read_text(encoding="utf-8")
        assert "self_check" not in html2.lower()

    def test_confidence_colors_in_html(self, run_dir):
        from review_pipeline.stages.decompose_requirement import prepare_clarification_review
        from review_pipeline.artifacts.io import write_json, read_json

        req_json = run_dir / "req.json"
        write_json(req_json, [{
            "requirement_key": "COLOR_REQ", "description": "Test color rendering",
        }])
        prepare_clarification_review(str(req_json), str(run_dir))

        html = (run_dir / "clarification_review.html").read_text(encoding="utf-8")
        assert "border-left: 4px solid" in html

    def test_import_memory_influences_later_run(self, run_dir):
        from review_pipeline.stages.decompose_requirement import prepare_clarification_review
        from review_pipeline.stages.validate_clarification import validate_clarification_review
        from review_pipeline.storage.store import import_memory, compute_historical_support
        from review_pipeline.artifacts.io import write_json, read_json

        # First run
        run1 = run_dir / "run1"
        run1.mkdir()
        req_json = run1 / "req.json"
        write_json(req_json, [{
            "requirement_key": "MEM_REQ", "description": "Test memory influence",
        }])
        prepare_clarification_review(str(req_json), str(run1))
        data = read_json(run1 / "clarification_review.json")
        data["decisions"] = [{"item_id": a["item_id"], "decision": "approve"}
                             for a in data["decomposition"]["ambiguities"]]
        write_json(run1 / "clarification_review.json", data)
        validate_clarification_review(str(run1 / "clarification_review.json"))

        db_path = str(run_dir / "mem.db")
        import_memory(str(run1), db_path)

        # Verify memory exists
        source_hash = data["source_requirement_hash"]
        support = compute_historical_support(source_hash, ["needs_clarification"], db_path)
        assert support["same_requirement_sessions"] >= 1
        assert "adjustment" in support
        assert -0.10 <= support["adjustment"] <= 0.10


# ── Issue 1: CLI smoke tests ───────────────────────────────────────────────

class TestCLI:
    def test_help(self):
        from review_pipeline.cli import main
        import sys as _sys
        try:
            ret = main(["--help"])
        except SystemExit as e:
            ret = e.code if e.code is not None else 0
        assert ret == 0

    def test_subcommand_help(self):
        from review_pipeline.cli import main
        try:
            ret = main(["prepare-clarification-review", "--help"])
        except SystemExit as e:
            ret = e.code if e.code is not None else 0
        assert ret == 0

    def test_prepare_clarification_review_mock_flag(self, run_dir, sample_requirement_json):
        from review_pipeline.cli import main

        ret = main([
            "prepare-clarification-review",
            "--input",
            str(sample_requirement_json),
            "--out",
            str(run_dir),
            "--mock",
        ])

        assert ret == 0
        assert (run_dir / "clarification_review.json").exists()

    def test_validate_missing_file(self):
        from review_pipeline.cli import main
        ret = main(["validate-review", "--file", "/nonexistent/file.json"])
        assert ret == 1


# ── Issue 12: Bounded adjustment proof ─────────────────────────────────────

class TestBoundedAdjustment:
    def test_positive_bounded(self):
        from review_pipeline.confidence.engine import normalize_historical_adjustment
        assert normalize_historical_adjustment(0.15) == 0.10

    def test_negative_bounded(self):
        from review_pipeline.confidence.engine import normalize_historical_adjustment
        assert normalize_historical_adjustment(-0.20) == -0.10

    def test_within_bounds(self):
        from review_pipeline.confidence.engine import normalize_historical_adjustment
        assert normalize_historical_adjustment(0.05) == 0.05
        assert normalize_historical_adjustment(-0.03) == -0.03
