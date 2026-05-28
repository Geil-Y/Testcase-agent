"""Tests for the simplified A/B/C reviewed pipeline (ADR-0005).

Covers: schemas, validators, prompt rendering without supplementary_info,
reviewed-only reads, blocking_gaps, LLM-C legacy-style prompts, regenerate.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def run_dir():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def sample_requirement():
    return {
        "requirement_key": "BMS_REQ_001",
        "description": "The BMS shall detect cell over-voltage and open the contactor within 100ms.",
        "function_name": "Cell Monitoring",
        "requirement_type": "requirement",
        "supplementary_info": "Cell voltage threshold: 4.25V",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Issue #38: Schema tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestExtractedTestBasisSchema:
    """Extracted test basis and reviewed counterpart share the same schema."""

    def test_section_item_known(self):
        from testcase_agent.review_pipeline.artifacts.models import SectionItem

        item = SectionItem(
            item_id="sig-1", status="known",
            content="CellVoltage", need="", source_text="cell voltage"
        )
        assert item.status == "known"
        assert item.content == "CellVoltage"
        assert item.need == ""

    def test_section_item_needs_review(self):
        from testcase_agent.review_pipeline.artifacts.models import SectionItem

        item = SectionItem(
            item_id="thr-1", status="needs_review",
            content="", need="Threshold value for over-voltage trigger",
            source_text="detect cell over-voltage"
        )
        assert item.status == "needs_review"
        assert item.need != ""
        assert item.content == ""

    def test_extracted_test_basis_has_five_sections(self):
        from testcase_agent.review_pipeline.artifacts.models import ExtractedTestBasis

        basis = ExtractedTestBasis(requirement_key="REQ_001")
        assert set(basis.sections.keys()) == {"signals", "thresholds", "timing", "states", "observations"}

    def test_extracted_test_basis_roundtrip(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.models import ExtractedTestBasis, SectionItem
        from testcase_agent.review_pipeline.artifacts.io import write_json, read_json

        basis = ExtractedTestBasis(
            requirement_key="REQ_001",
            source_description="Test requirement",
            sections={
                "signals": [
                    SectionItem(item_id="sig-1", status="known",
                                content="CellVoltage", source_text="cell voltage"),
                ],
                "thresholds": [
                    SectionItem(item_id="thr-1", status="needs_review",
                                need="Threshold value", source_text="over-voltage"),
                ],
                "timing": [],
                "states": [],
                "observations": [],
            },
            blocking_gaps=["Unclear trigger condition"],
        )

        path = run_dir / "extracted_test_basis.json"
        write_json(path, basis.model_dump())
        reloaded = ExtractedTestBasis(**read_json(path))

        assert reloaded.requirement_key == "REQ_001"
        assert len(reloaded.sections["signals"]) == 1
        assert reloaded.sections["signals"][0].status == "known"
        assert reloaded.sections["signals"][0].content == "CellVoltage"
        assert len(reloaded.sections["thresholds"]) == 1
        assert reloaded.sections["thresholds"][0].status == "needs_review"
        assert len(reloaded.blocking_gaps) == 1

    def test_reviewed_and_unreviewed_same_schema(self):
        """reviewed_extracted_test_basis.json uses the same schema as extracted_test_basis.json."""
        from testcase_agent.review_pipeline.artifacts.models import ExtractedTestBasis, SectionItem

        # Both use ExtractedTestBasis
        unreviewed = ExtractedTestBasis(requirement_key="R1",
            sections={"signals": [SectionItem(item_id="s1", status="known", content="X")],
                      "thresholds": [], "timing": [], "states": [], "observations": []})
        reviewed = ExtractedTestBasis(**unreviewed.model_dump())
        assert reviewed.model_dump() == unreviewed.model_dump()

    def test_case_intent_set_roundtrip(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.models import CaseIntentSet, CaseIntentItem
        from testcase_agent.review_pipeline.artifacts.io import write_json, read_json

        intent_set = CaseIntentSet(
            requirement_key="REQ_001",
            source_description="Test requirement",
            intents=[
                CaseIntentItem(intent_id="intent-1", coverage_dimension="normal_behavior",
                               intent_text="Verify normal operation"),
                CaseIntentItem(intent_id="intent-2", coverage_dimension="fault_or_protection",
                               intent_text="Verify over-voltage protection"),
            ],
            blocking_gaps=[],
        )

        path = run_dir / "case_intents.json"
        write_json(path, intent_set.model_dump())
        reloaded = CaseIntentSet(**read_json(path))

        assert len(reloaded.intents) == 2
        assert reloaded.intents[0].intent_id == "intent-1"
        assert reloaded.intents[0].coverage_dimension == "normal_behavior"
        assert "confidence_drivers" not in reloaded.intents[0].model_dump()

    def test_generated_case_set_roundtrip(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.models import GeneratedCaseSet, GeneratedCase
        from testcase_agent.review_pipeline.artifacts.io import write_json, read_json

        case_set = GeneratedCaseSet(
            requirement_key="REQ_001",
            cases=[GeneratedCase(
                case_id="case-1", title="Test OV trigger",
                objective="Verify over-voltage triggers contactor open",
                requirement_key="REQ_001", intent_id="intent-1",
                coverage_dimension="fault_or_protection",
            )],
        )

        path = run_dir / "generated_cases.json"
        write_json(path, [c.model_dump() for c in case_set.cases])
        reloaded = read_json(path)
        assert len(reloaded) == 1
        assert reloaded[0]["case_id"] == "case-1"


# ═══════════════════════════════════════════════════════════════════════════════
# Issue #38: Validator tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestValidators:
    """Downstream stages reject missing/blocked reviewed artifacts."""

    def test_reviewed_artifact_missing_fails(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.validation import validate_reviewed_artifact

        result = validate_reviewed_artifact(
            run_dir / "nonexistent.json", artifact_label="reviewed_extracted_test_basis.json")
        assert not result.is_valid
        assert "missing" in result.format_errors().lower()

    def test_reviewed_artifact_with_blocking_gaps_fails(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.io import write_json
        from testcase_agent.review_pipeline.artifacts.validation import validate_reviewed_artifact

        path = run_dir / "reviewed_extracted_test_basis.json"
        write_json(path, {
            "requirement_key": "R1",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
            "blocking_gaps": ["Non-testable heading row"],
        })

        result = validate_reviewed_artifact(path, artifact_label="reviewed_extracted_test_basis.json")
        assert not result.is_valid
        assert "blocking_gaps" in result.format_errors().lower()
        assert "Non-testable heading row" in result.format_errors()

    def test_accept_all_blocked_by_blocking_gaps(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.io import write_json
        from testcase_agent.review_pipeline.artifacts.validation import validate_accept_all_no_blocking_gaps

        path = run_dir / "extracted_test_basis.json"
        write_json(path, {
            "requirement_key": "R1",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
            "blocking_gaps": ["Unclear trigger"],
        })

        result = validate_accept_all_no_blocking_gaps(path, artifact_label="extracted_test_basis.json")
        assert not result.is_valid
        assert "cannot accept all" in result.format_errors().lower()
        assert "Unclear trigger" in result.format_errors()

    def test_accept_all_passes_without_blocking_gaps(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.io import write_json
        from testcase_agent.review_pipeline.artifacts.validation import validate_accept_all_no_blocking_gaps

        path = run_dir / "extracted_test_basis.json"
        write_json(path, {
            "requirement_key": "R1",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
            "blocking_gaps": [],
        })

        result = validate_accept_all_no_blocking_gaps(path, artifact_label="extracted_test_basis.json")
        assert result.is_valid

    def test_legacy_run_dir_detection(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.validation import is_legacy_run_dir

        # No legacy artifacts
        assert not is_legacy_run_dir(run_dir)

        # Add a legacy artifact
        (run_dir / "clarification_review.json").write_text("{}")
        assert is_legacy_run_dir(run_dir)

    def test_legacy_unsupported_message(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.validation import get_legacy_unsupported_message

        (run_dir / "clarification_review.json").write_text("{}")
        msg = get_legacy_unsupported_message(run_dir)
        assert "legacy" in msg.lower()
        assert "regenerate" in msg.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Issue #39: LLM-A extraction
# ═══════════════════════════════════════════════════════════════════════════════

class TestLLMAExtraction:
    """LLM-A extracts 5 sections, no facts/ambiguities, no supplementary_info."""

    def test_extract_placeholder_produces_valid_basis(self, run_dir, sample_requirement):
        from testcase_agent.review_pipeline.artifacts.io import read_json, write_json
        from testcase_agent.review_pipeline.stages.extract_test_basis import extract_test_basis

        req_path = run_dir / "requirements.json"
        write_json(req_path, [sample_requirement])

        basis = extract_test_basis(str(req_path), str(run_dir))
        assert basis.requirement_key == "BMS_REQ_001"
        assert set(basis.sections.keys()) == {"signals", "thresholds", "timing", "states", "observations"}

        # Check output file exists
        output = read_json(run_dir / "extracted_test_basis.json")
        assert output["requirement_key"] == "BMS_REQ_001"

    def test_facts_and_ambiguities_not_in_output(self, run_dir, sample_requirement):
        from testcase_agent.review_pipeline.artifacts.io import read_json, write_json
        from testcase_agent.review_pipeline.stages.extract_test_basis import extract_test_basis

        req_path = run_dir / "requirements.json"
        write_json(req_path, [sample_requirement])

        extract_test_basis(str(req_path), str(run_dir))
        output = read_json(run_dir / "extracted_test_basis.json")

        assert "facts" not in output
        assert "ambiguities" not in output
        assert "clarification_questions" not in output
        assert "confidence_drivers" not in output
        assert "safe_generation_policy" not in output
        assert "sections" in output

    def test_accept_all_writes_reviewed(self, run_dir, sample_requirement):
        from testcase_agent.review_pipeline.artifacts.io import read_json, write_json
        from testcase_agent.review_pipeline.stages.extract_test_basis import extract_test_basis, accept_extraction

        req_path = run_dir / "requirements.json"
        write_json(req_path, [sample_requirement])

        extract_test_basis(str(req_path), str(run_dir))
        basis = accept_extraction(run_dir)

        reviewed = read_json(run_dir / "reviewed_extracted_test_basis.json")
        assert reviewed["requirement_key"] == "BMS_REQ_001"
        assert "sections" in reviewed
        assert reviewed["blocking_gaps"] == []

    def test_accept_all_rejects_blocking_gaps(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.io import write_json
        from testcase_agent.review_pipeline.stages.extract_test_basis import accept_extraction

        write_json(run_dir / "extracted_test_basis.json", {
            "requirement_key": "R1",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
            "blocking_gaps": ["Test blocking gap"],
        })

        with pytest.raises(ValueError, match="blocking"):
            accept_extraction(run_dir)

    def test_apply_review_actions_edit(self, run_dir, sample_requirement):
        from testcase_agent.review_pipeline.artifacts.io import read_json, write_json
        from testcase_agent.review_pipeline.artifacts.models import ExtractionReviewAction, SectionItem
        from testcase_agent.review_pipeline.stages.extract_test_basis import extract_test_basis, apply_extraction_review

        req_path = run_dir / "requirements.json"
        write_json(req_path, [sample_requirement])

        extract_test_basis(str(req_path), str(run_dir))

        edited_item = SectionItem(
            item_id="thr-1", status="known",
            content="4.25V", need="", source_text="edited by human"
        )
        actions = [ExtractionReviewAction(
            item_id="thr-1", section="thresholds", action="edit",
            edited_item=edited_item
        )]
        basis = apply_extraction_review(run_dir, actions)

        thresholds = basis.sections["thresholds"]
        assert len(thresholds) == 1
        assert thresholds[0].status == "known"
        assert thresholds[0].content == "4.25V"

    def test_apply_review_actions_remove(self, run_dir, sample_requirement):
        from testcase_agent.review_pipeline.artifacts.io import write_json
        from testcase_agent.review_pipeline.artifacts.models import ExtractionReviewAction
        from testcase_agent.review_pipeline.stages.extract_test_basis import extract_test_basis, apply_extraction_review

        req_path = run_dir / "requirements.json"
        write_json(req_path, [sample_requirement])

        extract_test_basis(str(req_path), str(run_dir))

        # Remove all threshold items
        actions = [ExtractionReviewAction(item_id="thr-1", section="thresholds", action="remove")]
        basis = apply_extraction_review(run_dir, actions)

        thresholds = basis.sections["thresholds"]
        assert len(thresholds) == 0

    def test_apply_review_actions_add(self, run_dir, sample_requirement):
        from testcase_agent.review_pipeline.artifacts.io import write_json
        from testcase_agent.review_pipeline.artifacts.models import ExtractionReviewAction, SectionItem
        from testcase_agent.review_pipeline.stages.extract_test_basis import extract_test_basis, apply_extraction_review

        req_path = run_dir / "requirements.json"
        write_json(req_path, [sample_requirement])

        extract_test_basis(str(req_path), str(run_dir))

        new_item = SectionItem(item_id="new-1", status="known",
                               content="ContactorState", source_text="added by human")
        actions = [ExtractionReviewAction(
            item_id="new-1", section="signals", action="add",
            new_item=new_item
        )]
        basis = apply_extraction_review(run_dir, actions)

        signals = basis.sections["signals"]
        assert len(signals) >= 1
        assert any(s.item_id == "new-1" for s in signals)


# ═══════════════════════════════════════════════════════════════════════════════
# Issue #40: LLM-B intent planning from reviewed extraction
# ═══════════════════════════════════════════════════════════════════════════════

class TestLLMBPlanning:
    """LLM-B reads reviewed extraction only, not raw extraction."""

    def test_plan_rejects_missing_reviewed_extraction(self, run_dir):
        from testcase_agent.review_pipeline.stages.plan_case_intents import plan_intents

        with pytest.raises(ValueError, match="missing"):
            plan_intents(run_dir)

    def test_plan_blocks_on_blocking_gaps(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.io import write_json
        from testcase_agent.review_pipeline.stages.plan_case_intents import plan_intents

        write_json(run_dir / "reviewed_extracted_test_basis.json", {
            "requirement_key": "R1",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
            "blocking_gaps": ["Blocked requirement"],
        })

        with pytest.raises(ValueError, match="blocking"):
            plan_intents(run_dir)

    def test_plan_placeholder_from_reviewed(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.io import write_json
        from testcase_agent.review_pipeline.stages.plan_case_intents import plan_intents

        write_json(run_dir / "reviewed_extracted_test_basis.json", {
            "requirement_key": "R1",
            "source_description": "Test requirement description",
            "sections": {
                "signals": [{"item_id": "s1", "status": "known", "content": "CellVoltage", "need": "", "source_text": "test"}],
                "thresholds": [{"item_id": "t1", "status": "needs_review", "content": "", "need": "Threshold value", "source_text": "test"}],
                "timing": [],
                "states": [],
                "observations": [],
            },
            "blocking_gaps": [],
        })

        result = plan_intents(run_dir)
        assert len(result.intents) >= 1
        assert result.intents[0].intent_id == "intent-1"
        assert result.intents[0].coverage_dimension != ""

    def test_accept_intents_writes_reviewed(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.io import write_json, read_json
        from testcase_agent.review_pipeline.stages.plan_case_intents import plan_intents, accept_intents

        write_json(run_dir / "reviewed_extracted_test_basis.json", {
            "requirement_key": "R1",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
            "blocking_gaps": [],
        })

        plan_intents(run_dir)
        accept_intents(run_dir)

        reviewed = read_json(run_dir / "reviewed_case_intents.json")
        assert reviewed["requirement_key"] == "R1"
        assert len(reviewed["intents"]) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Issue #41: LLM-C legacy-style inputs
# ═══════════════════════════════════════════════════════════════════════════════

class TestLLMCLegacyStyleInputs:
    """LLM-C prompt renders legacy-style known sections and unresolved items."""

    def test_prompt_renders_legacy_known_sections(self):
        from testcase_agent.review_pipeline.prompts import render_prompt

        system, user = render_prompt(
            "write_case",
            requirement_key="REQ_001",
            description="Test requirement",
            intent_id="intent-1",
            coverage_dimension="normal_behavior",
            intent_text="Verify normal operation",
            known_signals="- [sig-1] CellVoltage",
            known_thresholds="- [thr-1] r_CellOV_Threshold",
            known_timing="- [tim-1] t_CellOV_Debounce",
            known_states="- [st-1] HV_ON",
            known_observations="- [obs-1] DTC_CellOV",
            unresolved_items="- [thr-2] Response delay value",
            review_comment="",
        )

        assert "Known BMS Signals" in user
        assert "CellVoltage" in user
        assert "Known Thresholds" in user
        assert "r_CellOV_Threshold" in user
        assert "Known Timing Parameters" in user
        assert "t_CellOV_Debounce" in user
        assert "Known BMS States" in user
        assert "HV_ON" in user
        assert "Known Observation Points" in user
        assert "DTC_CellOV" in user
        assert "Critical Missing Information" in user
        assert "Unresolved Items" in user
        assert "Response delay value" in user

    def test_prompt_excludes_supplementary_info(self):
        """supplementary_info must NOT appear in LLM-C user prompt."""
        from testcase_agent.review_pipeline.prompts import render_prompt

        _, user = render_prompt(
            "write_case",
            requirement_key="REQ_001",
            description="Test requirement",
            intent_id="intent-1",
            coverage_dimension="normal_behavior",
            intent_text="Verify normal operation",
            known_signals="", known_thresholds="", known_timing="",
            known_states="", known_observations="", unresolved_items="",
            review_comment="",
        )

        assert "Supplementary" not in user
        assert "supplementary" not in user

    def test_prompt_includes_review_comment(self):
        from testcase_agent.review_pipeline.prompts import render_prompt

        _, user = render_prompt(
            "write_case",
            requirement_key="REQ_001",
            description="Test requirement",
            intent_id="intent-1",
            coverage_dimension="normal_behavior",
            intent_text="Verify normal operation",
            known_signals="", known_thresholds="", known_timing="",
            known_states="", known_observations="", unresolved_items="",
            review_comment="Make steps more detailed for timing verification",
        )

        assert "Review Comment" in user
        assert "Make steps more detailed" in user
        assert "Do not introduce new signals" in user

    def test_prompt_renders_unresolved_items_only(self):
        """Unresolved items section should appear only when items exist."""
        from testcase_agent.review_pipeline.prompts import render_prompt

        _, user_with = render_prompt(
            "write_case",
            requirement_key="REQ_001", description="Test",
            intent_id="i1", coverage_dimension="normal_behavior",
            intent_text="Verify", known_signals="", known_thresholds="",
            known_timing="", known_states="", known_observations="",
            unresolved_items="- [thr-1] Missing threshold value",
            review_comment="",
        )
        assert "Unresolved Items" in user_with

        _, user_without = render_prompt(
            "write_case",
            requirement_key="REQ_001", description="Test",
            intent_id="i1", coverage_dimension="normal_behavior",
            intent_text="Verify", known_signals="", known_thresholds="",
            known_timing="", known_states="", known_observations="",
            unresolved_items="",
            review_comment="",
        )
        assert "Unresolved Items" not in user_without


# ═══════════════════════════════════════════════════════════════════════════════
# Issue #42: Reviewed cases Accept/Edit flow
# ═══════════════════════════════════════════════════════════════════════════════

class TestReviewedCasesFlow:
    """generated_cases.json -> reviewed_cases.json via Accept All or Edit."""

    def test_accept_cases_writes_reviewed(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.io import write_json, read_json
        from testcase_agent.review_pipeline.stages.write_cases import accept_cases

        write_json(run_dir / "generated_cases.json", {
            "requirement_key": "R1",
            "cases": [{
                "case_id": "case-1", "title": "Test", "objective": "Verify",
                "requirement_key": "R1", "intent_id": "i1",
                "coverage_dimension": "normal_behavior",
            }],
        })

        result = accept_cases(run_dir)
        assert len(result.cases) == 1

        reviewed = read_json(run_dir / "reviewed_cases.json")
        assert "cases" in reviewed
        assert len(reviewed["cases"]) == 1

    def test_edit_cases_writes_reviewed(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.io import write_json, read_json
        from testcase_agent.review_pipeline.stages.write_cases import edit_cases

        write_json(run_dir / "generated_cases.json", {
            "requirement_key": "R1",
            "cases": [{"case_id": "case-1", "title": "Test"}],
        })
        write_json(run_dir / "reviewed_extracted_test_basis.json", {
            "requirement_key": "R1",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
            "blocking_gaps": [],
        })

        cases = [{"case_id": "case-1", "title": "Edited title",
                   "objective": "Edited", "requirement_key": "R1",
                   "intent_id": "i1", "coverage_dimension": "normal_behavior"}]
        result = edit_cases(run_dir, cases)
        assert len(result.cases) == 1
        assert result.cases[0].title == "Edited title"

        reviewed = read_json(run_dir / "reviewed_cases.json")
        assert reviewed["cases"][0]["title"] == "Edited title"


# ═══════════════════════════════════════════════════════════════════════════════
# Issue #43: Regenerate with review comment
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegenerate:
    """Regenerate uses reviewed artifacts + comment only."""

    def test_regenerate_rejects_missing_reviewed_extraction(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.models import RegenerateRequest
        from testcase_agent.review_pipeline.stages.write_cases import regenerate_case

        with pytest.raises(ValueError, match="missing"):
            regenerate_case(run_dir, RegenerateRequest(
                case_id="case-1", intent_id="intent-1",
                review_comment="Fix wording",
            ))

    def test_regenerate_rejects_missing_reviewed_intents(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.io import write_json
        from testcase_agent.review_pipeline.artifacts.models import RegenerateRequest
        from testcase_agent.review_pipeline.stages.write_cases import regenerate_case

        write_json(run_dir / "reviewed_extracted_test_basis.json", {
            "requirement_key": "R1",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
            "blocking_gaps": [],
        })

        with pytest.raises(ValueError, match="missing"):
            regenerate_case(run_dir, RegenerateRequest(
                case_id="case-1", intent_id="intent-1",
                review_comment="Fix",
            ))

    def test_regenerate_with_placeholder(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.io import write_json
        from testcase_agent.review_pipeline.artifacts.models import RegenerateRequest
        from testcase_agent.review_pipeline.stages.write_cases import regenerate_case

        write_json(run_dir / "reviewed_extracted_test_basis.json", {
            "requirement_key": "R1",
            "source_description": "Test requirement",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
            "blocking_gaps": [],
        })
        write_json(run_dir / "reviewed_case_intents.json", {
            "requirement_key": "R1",
            "intents": [
                {"intent_id": "intent-1", "coverage_dimension": "normal_behavior",
                 "intent_text": "Verify normal op"},
            ],
            "blocking_gaps": [],
        })

        case = regenerate_case(run_dir, RegenerateRequest(
            case_id="case-existing", intent_id="intent-1",
            review_comment="Improve step clarity",
        ))
        assert case.case_id == "case-existing"

    def test_regenerate_rejects_unknown_intent(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.io import write_json
        from testcase_agent.review_pipeline.artifacts.models import RegenerateRequest
        from testcase_agent.review_pipeline.stages.write_cases import regenerate_case

        write_json(run_dir / "reviewed_extracted_test_basis.json", {
            "requirement_key": "R1",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
            "blocking_gaps": [],
        })
        write_json(run_dir / "reviewed_case_intents.json", {
            "requirement_key": "R1",
            "intents": [
                {"intent_id": "intent-1", "coverage_dimension": "normal_behavior",
                 "intent_text": "Verify normal"},
            ],
            "blocking_gaps": [],
        })

        with pytest.raises(ValueError, match="not found"):
            regenerate_case(run_dir, RegenerateRequest(
                case_id="case-1", intent_id="intent-nonexistent",
                review_comment="Fix",
            ))


# ═══════════════════════════════════════════════════════════════════════════════
# Issue #44 & #45: supplementary_info exclusion from all prompts
# ═══════════════════════════════════════════════════════════════════════════════

class TestSupplementaryInfoExclusion:
    """supplementary_info must NOT appear in any LLM prompt."""

    def test_extraction_prompt_excludes_supplementary(self):
        from testcase_agent.review_pipeline.prompts import render_prompt

        _, user = render_prompt(
            "extract_test_basis",
            requirement_key="R1",
            description="Test requirement",
            function_name="Test",
            requirement_type="requirement",
        )

        assert "Supplementary" not in user
        assert "supplementary" not in user
        assert "Supplementary Information" not in user

    def test_planning_prompt_excludes_supplementary(self):
        from testcase_agent.review_pipeline.prompts import render_prompt

        _, user = render_prompt(
            "plan_intents",
            requirement_key="R1",
            description="Test requirement",
            known_signals="",
            known_thresholds="",
            known_timing="",
            known_states="",
            known_observations="",
            unresolved_items="",
        )

        assert "Supplementary" not in user
        assert "supplementary" not in user

    def test_write_case_prompt_excludes_supplementary(self):
        from testcase_agent.review_pipeline.prompts import render_prompt

        _, user = render_prompt(
            "write_case",
            requirement_key="R1",
            description="Test requirement",
            intent_id="i1",
            coverage_dimension="normal_behavior",
            intent_text="Verify",
            known_signals="",
            known_thresholds="",
            known_timing="",
            known_states="",
            known_observations="",
            unresolved_items="",
            review_comment="",
        )

        assert "Supplementary" not in user
        assert "supplementary" not in user


# ═══════════════════════════════════════════════════════════════════════════════
# Blocking gaps tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestBlockingGaps:
    """blocking_gaps prevent downstream stages."""

    def test_extracted_test_basis_detects_blocking_gaps(self):
        from testcase_agent.review_pipeline.artifacts.models import ExtractedTestBasis

        basis = ExtractedTestBasis(requirement_key="R1", blocking_gaps=["Gap 1"])
        assert basis.has_blocking_gaps

        basis2 = ExtractedTestBasis(requirement_key="R1", blocking_gaps=[])
        assert not basis2.has_blocking_gaps

    def test_case_intent_set_detects_blocking_gaps(self):
        from testcase_agent.review_pipeline.artifacts.models import CaseIntentSet

        intent_set = CaseIntentSet(requirement_key="R1", blocking_gaps=["Blocked"])
        assert intent_set.has_blocking_gaps

        intent_set2 = CaseIntentSet(requirement_key="R1", blocking_gaps=[])
        assert not intent_set2.has_blocking_gaps

    def test_downstream_validate_detects_blocking(self, run_dir):
        from testcase_agent.review_pipeline.artifacts.io import write_json
        from testcase_agent.review_pipeline.artifacts.validation import validate_downstream_run

        # First: no legacy, no reviewed - fails
        result = validate_downstream_run(run_dir, "plan_intents")
        assert not result.is_valid
        assert "missing" in result.format_errors().lower()

        # Write reviewed with blocking gaps
        write_json(run_dir / "reviewed_extracted_test_basis.json", {
            "requirement_key": "R1",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
            "blocking_gaps": ["Non-testable requirement"],
        })

        result2 = validate_downstream_run(run_dir, "plan_intents")
        assert not result2.is_valid
        assert "blocking_gaps" in result2.format_errors().lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Helper methods on models
# ═══════════════════════════════════════════════════════════════════════════════

class TestModelHelpers:
    def test_known_items_filter(self):
        from testcase_agent.review_pipeline.artifacts.models import ExtractedTestBasis, SectionItem

        basis = ExtractedTestBasis(requirement_key="R1",
            sections={
                "signals": [
                    SectionItem(item_id="s1", status="known", content="SignalA"),
                    SectionItem(item_id="s2", status="needs_review", need="Missing signal"),
                ],
                "thresholds": [], "timing": [], "states": [], "observations": [],
            })

        known = basis.known_items("signals")
        assert len(known) == 1
        assert known[0].item_id == "s1"
        assert known[0].content == "SignalA"

    def test_needs_review_items_filter(self):
        from testcase_agent.review_pipeline.artifacts.models import ExtractedTestBasis, SectionItem

        basis = ExtractedTestBasis(requirement_key="R1",
            sections={
                "signals": [
                    SectionItem(item_id="s1", status="known", content="SignalA"),
                    SectionItem(item_id="s2", status="needs_review", need="Missing signal"),
                ],
                "thresholds": [], "timing": [], "states": [], "observations": [],
            })

        needs = basis.needs_review_items("signals")
        assert len(needs) == 1
        assert needs[0].item_id == "s2"

    def test_all_needs_review_items_across_sections(self):
        from testcase_agent.review_pipeline.artifacts.models import ExtractedTestBasis, SectionItem

        basis = ExtractedTestBasis(requirement_key="R1",
            sections={
                "signals": [SectionItem(item_id="s1", status="needs_review", need="Missing signal")],
                "thresholds": [SectionItem(item_id="t1", status="needs_review", need="Missing threshold")],
                "timing": [], "states": [], "observations": [],
            })

        all_needs = basis.all_needs_review_items()
        assert len(all_needs) == 2
