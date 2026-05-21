"""Tests for v2 Section 3 hard gates and missing information evaluation."""

from optimization.evaluator import (
    CHECKLIST,
    evaluate_case,
    evaluate_generated_cases,
    evaluate_missing_info_hard_gates,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _case(title="TC-01", objective="Verify X", precondition="Ready", postcondition="Done",
          steps=None, raw_html="", related_requirement="REQ-001"):
    return {
        "title": title,
        "objective": objective,
        "precondition": precondition,
        "postcondition": postcondition,
        "steps": steps or [],
        "raw_html": raw_html,
        "related_requirement": related_requirement,
    }


def _step(order=1, action="Do something", expected="OK"):
    return {"order": order, "action": action, "expected": expected}


def _req_info(**overrides):
    info = {
        "signals": [],
        "thresholds": [],
        "timing": [],
        "case_coverage": "normal_behavior",
        "requirement_description": "",
        "supplementary_info": "",
        "expected_missing_categories": [],
    }
    info.update(overrides)
    return info


# ── Evaluation Engine interface ─────────────────────────────────────────


class TestEvaluateGeneratedCases:
    def test_returns_case_results_counts_and_hard_gate_records(self):
        data = [{
            "requirement_key": "REQ-001",
            "evaluation_bucket": "missing-info-trap",
            "expected_missing_categories": ["threshold"],
            "description": "Timing is not specified.",
            "supplementary_info": "",
            "analysis": {
                "signals": [],
                "thresholds": [],
                "timing": [],
                "missing_info_items": [],
                "case_intents": [{"coverage": "normal_behavior"}],
            },
            "cases": [
                _case(
                    title="TC missing marker",
                    precondition="BMS initialized, all parameters within normal operating range, no active faults.",
                    postcondition="System returned to normal operating state.",
                    steps=[_step(action="Set voltage to 100V", expected="Protection flag becomes active")],
                )
            ],
        }]

        result = evaluate_generated_cases(data)

        assert result.total_cases == 1
        assert result.total_passed == 0
        assert result.case_pass_rate == 0.0
        assert result.case_results[("REQ-001", 0)].failed_items == ["2.2.1", "3.2.1", "3.2.2", "4.1.1"]
        assert result.item_fail_counts["2.2.1"] == 1
        assert result.item_fail_counts["3.2.1"] == 1
        assert result.item_fail_counts["3.2.2"] == 1
        assert result.item_fail_counts["4.1.1"] == 1
        assert result.hard_gate_records[0]["item_ids"] == ["3.2.1"]


# ── Section 3 item IDs in CHECKLIST ─────────────────────────────────────


def test_checklist_has_v2_section3_items():
    assert "3.2.1" in CHECKLIST
    assert "3.2.2" in CHECKLIST
    assert "3.2.3" in CHECKLIST
    assert "3.3.1" in CHECKLIST
    assert "3.3.2" in CHECKLIST
    assert "3.3.3" in CHECKLIST
    assert "[HARD]" in CHECKLIST["3.2.1"][0]
    assert "[HARD]" in CHECKLIST["3.2.2"][0]
    assert "[HARD]" in CHECKLIST["3.2.3"][0]


# ── 3.2.1 [HARD] — needs signal/threshold/timing/state/observation but
#    case lacks [NEEDS REVIEW] ────────────────────────────────────────────


class TestHardGateMissingNeedsReview:
    def test_fails_when_expected_missing_but_no_nr_in_steps(self):
        case = _case(steps=[_step(action="Set voltage to threshold", expected="Flag set")])
        info = _req_info(expected_missing_categories=["threshold", "timing"])
        failed, warnings = evaluate_case(case, info, {})
        assert "3.2.1" in failed

    def test_passes_when_expected_missing_and_nr_in_steps(self):
        case = _case(steps=[
            _step(action="Wait [NEEDS REVIEW] ms", expected=None),
            _step(action="Check flag", expected="Flag == 1"),
        ])
        info = _req_info(expected_missing_categories=["timing"])
        failed, warnings = evaluate_case(case, info, {})
        assert "3.2.1" not in failed

    def test_skipped_when_no_expected_missing_categories(self):
        """Without Prompt Evaluation Set metadata, 3.2.1 cannot fire."""
        case = _case(steps=[_step(action="Set voltage", expected="OK")])
        info = _req_info(expected_missing_categories=[])
        failed, warnings = evaluate_case(case, info, {})
        assert "3.2.1" not in failed


# ── 3.2.2 [HARD] — action/expected invents missing semantics ─────────────


class TestHardGateInventedSemantics:
    def test_fails_when_threshold_expected_missing_but_case_has_number(self):
        case = _case(steps=[_step(action="Set voltage to 4.2V", expected="Flag set")])
        info = _req_info(expected_missing_categories=["threshold"])
        failed, warnings = evaluate_case(case, info, {})
        assert "3.2.2" in failed

    def test_passes_when_threshold_missing_but_value_replaced_with_nr(self):
        case = _case(steps=[_step(action="Set voltage to [NEEDS REVIEW]", expected="Flag set")])
        info = _req_info(expected_missing_categories=["threshold"])
        failed, warnings = evaluate_case(case, info, {})
        assert "3.2.2" not in failed

    def test_not_triggered_when_threshold_not_in_expected_missing(self):
        case = _case(steps=[_step(action="Set voltage to 4.2V", expected="OK")])
        info = _req_info(expected_missing_categories=["timing"])
        failed, warnings = evaluate_case(case, info, {})
        assert "3.2.2" not in failed

    def test_fails_when_expected_uses_related_context_identifier_not_in_requirement(self):
        case = _case(steps=[
            _step(
                action="Set cell voltage above r_CellOV_Threshold",
                expected="BMS_CellOV_L3_Flag == 1 & DTC_Overvoltage set",
            )
        ])
        info = _req_info(
            signals=["BMS_CellOV_Detect", "BMS_CellOV_L3_Flag"],
            thresholds=["r_CellOV_Threshold"],
            requirement_description=(
                "The BMS shall monitor each cell voltage against the "
                "overvoltage threshold. BMS_CellOV_Detect shall be set to 1 "
                "when any cell voltage >= r_CellOV_Threshold."
            ),
            supplementary_info=(
                "Related context: BMS_CellOV_L3_Flag and DTC_Overvoltage are "
                "used by severe overvoltage requirements."
            ),
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "2.1.2" in failed

    def test_accepts_expected_identifier_from_explicit_accepted_test_basis(self):
        case = _case(steps=[
            _step(
                action="Set discharge request active",
                expected="BMS_DischargeLimitReq == 1",
            )
        ])
        info = _req_info(
            signals=["BMS_CellUV_Flag"],
            requirement_description=(
                "IF any cell voltage <= 2.80 V THEN BMS_CellUV_Flag := 1 "
                "and limit discharge power."
            ),
            accepted_test_basis="Observable evidence: BMS_DischargeLimitReq.",
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "2.1.2" not in failed

    def test_fails_when_action_uses_related_context_identifier_not_in_requirement(self):
        case = _case(steps=[
            _step(
                action="Set BMS_CellOV_L3_Flag to 1",
                expected="BMS_CellOV_Detect == 1",
            )
        ])
        info = _req_info(
            signals=["BMS_CellOV_Detect"],
            requirement_description=(
                "BMS_CellOV_Detect shall be set to 1 when any cell voltage "
                ">= r_CellOV_Threshold."
            ),
            supplementary_info="Related context: BMS_CellOV_L3_Flag.",
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "2.1.2" in failed

    def test_accepts_natural_language_outcome_with_needs_review_when_observation_missing(self):
        case = _case(steps=[
            _step(
                action="Disconnect charger",
                expected="charging is prevented [NEEDS REVIEW]",
            )
        ])
        info = _req_info(
            signals=["BMS_ChargeEnable"],
            expected_missing_categories=["observation"],
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "2.1.1" not in failed
        assert "3.2.1" not in failed


# ── 3.2.3 [WARNING] — complete requirement but case adds [NEEDS REVIEW] ──


class TestHardGateUnnecessaryNeedsReview:
    def test_fails_when_nr_present_but_no_expected_missing(self):
        case = _case(steps=[_step(action="Set [NEEDS REVIEW]", expected="OK")])
        info = _req_info(expected_missing_categories=[])
        failed, warnings = evaluate_case(case, info, {})
        assert "3.2.3" in failed
        assert "3.2.3" not in warnings

    def test_passes_when_nr_present_and_expected_missing_exists(self):
        case = _case(steps=[_step(action="Set [NEEDS REVIEW]", expected="OK")])
        info = _req_info(expected_missing_categories=["timing"])
        failed, warnings = evaluate_case(case, info, {})
        assert "3.2.3" not in failed

    def test_passes_when_no_nr(self):
        case = _case(steps=[_step(action="Set voltage", expected="OK")])
        info = _req_info(expected_missing_categories=[])
        failed, warnings = evaluate_case(case, info, {})
        assert "3.2.3" not in failed


# ── 3.3.1 — [NEEDS REVIEW] only in action/expected, not elsewhere ───────


class TestNeedsReviewPosition:
    def test_fails_when_nr_in_title(self):
        case = _case(title="[NEEDS REVIEW] check")
        failed, warnings = evaluate_case(case, _req_info(), {})
        assert "3.3.1" in failed

    def test_fails_when_nr_in_objective(self):
        case = _case(objective="Verify [NEEDS REVIEW] behavior")
        failed, warnings = evaluate_case(case, _req_info(), {})
        assert "3.3.1" in failed

    def test_fails_when_nr_in_precondition(self):
        case = _case(precondition="BMS at [NEEDS REVIEW] state")
        failed, warnings = evaluate_case(case, _req_info(), {})
        assert "3.3.1" in failed

    def test_passes_when_nr_only_in_action(self):
        case = _case(steps=[_step(action="Set [NEEDS REVIEW]", expected="OK")])
        failed, warnings = evaluate_case(case, _req_info(), {})
        assert "3.3.1" not in failed


# ── 3.3.2 — timing missing → [NEEDS REVIEW] in Wait action ───────────────


class TestNeedsReviewInWaitAction:
    def test_fails_when_timing_missing_but_nr_not_in_wait(self):
        case = _case(steps=[
            _step(action="Set value", expected="[NEEDS REVIEW]"),
        ])
        info = _req_info(expected_missing_categories=["timing"])
        failed, warnings = evaluate_case(case, info, {})
        assert "3.3.2" in failed

    def test_passes_when_timing_missing_and_nr_in_wait_action(self):
        case = _case(steps=[
            _step(action="Wait [NEEDS REVIEW] ms", expected=None),
        ])
        info = _req_info(expected_missing_categories=["timing"])
        failed, warnings = evaluate_case(case, info, {})
        assert "3.3.2" not in failed

    def test_passes_when_timing_missing_and_wait_action_has_response_expected(self):
        case = _case(steps=[
            _step(action="Wait response time [NEEDS REVIEW]", expected="BMS_CellOV_Detect := 1"),
        ])
        info = _req_info(
            expected_missing_categories=["timing"],
            requirement_description="BMS_CellOV_Detect shall be set to 1.",
        )
        failed, warnings = evaluate_case(case, info, {})
        assert "3.3.2" not in failed
        assert "4.1.1" not in failed
        assert "4.1.1" not in warnings

    def test_not_triggered_when_timing_not_in_expected_missing(self):
        case = _case(steps=[_step(action="Set value", expected="[NEEDS REVIEW]")])
        info = _req_info(expected_missing_categories=["threshold"])
        failed, warnings = evaluate_case(case, info, {})
        assert "3.3.2" not in failed


# ── 3.3.3 — no [NEEDS REVIEW: category] suffix ──────────────────────────


class TestWarningNeedsReviewSuffix:
    def test_warns_when_suffix_in_action(self):
        case = _case(steps=[_step(action="Set [NEEDS REVIEW: timing] wait", expected="OK")])
        failed, warnings = evaluate_case(case, _req_info(), {})
        assert "3.3.3" in warnings

    def test_warns_when_suffix_in_raw_html(self):
        case = _case(raw_html="<action>[NEEDS REVIEW: signal] check</action>")
        failed, warnings = evaluate_case(case, _req_info(), {})
        assert "3.3.3" in warnings

    def test_passes_when_bare_nr(self):
        case = _case(steps=[_step(action="Set [NEEDS REVIEW]", expected="OK")])
        failed, warnings = evaluate_case(case, _req_info(), {})
        assert "3.3.3" not in warnings


# ── Good-case calibration regressions ───────────────────────────────────


class TestGoodCaseCalibrationRegressions:
    def test_fails_when_set_step_immediately_expects_bms_response(self):
        case = _case(steps=[
            _step(
                action="Set cell voltage above r_CellOV_Threshold [NEEDS REVIEW]",
                expected="BMS_CellOV_Detect := 1",
            ),
            _step(action="Wait raw detection response time [NEEDS REVIEW]", expected=None),
        ])
        info = _req_info(
            signals=["BMS_CellOV_Detect"],
            expected_missing_categories=["signal", "timing"],
            requirement_description=(
                "BMS_CellOV_Detect shall be set to 1 when any cell voltage "
                ">= r_CellOV_Threshold."
            ),
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "4.1.1" in failed

    def test_allows_set_step_expected_to_confirm_stimulus_condition(self):
        case = _case(steps=[
            _step(
                action="Set cell voltage below r_CellOV_Threshold [NEEDS REVIEW]",
                expected="Cell voltage is below r_CellOV_Threshold [NEEDS REVIEW]",
            ),
            _step(
                action="Wait raw detection response time [NEEDS REVIEW]",
                expected="BMS_CellOV_Detect == 0",
            ),
        ])
        info = _req_info(
            signals=["BMS_CellOV_Detect"],
            expected_missing_categories=["signal", "timing"],
            requirement_description=(
                "BMS_CellOV_Detect shall be set to 1 when any cell voltage "
                ">= r_CellOV_Threshold."
            ),
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "4.1.1" not in failed

    def test_empty_needs_review_expected_is_not_judgeable(self):
        case = _case(steps=[
            _step(action="Set charger connection state", expected="[NEEDS REVIEW]"),
        ])
        info = _req_info(expected_missing_categories=["observation"])

        failed, warnings = evaluate_case(case, info, {})

        assert "4.2.3" in failed

    def test_fails_when_case_expects_no_trigger_at_inclusive_lower_boundary(self):
        case = _case(steps=[
            _step(action="Set cell voltage to 2.80 V", expected="BMS_CellUV_Flag == 0"),
        ])
        info = _req_info(
            signals=["BMS_CellUV_Flag"],
            requirement_description=(
                "IF any cell voltage <= 2.80 V THEN BMS_CellUV_Flag := 1 "
                "and limit discharge power."
            ),
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "5.1.1" in failed

    def test_fails_when_natural_language_inclusive_boundary_expects_no_trigger(self):
        case = _case(steps=[
            _step(action="Set cell voltage to 2.80 V", expected="BMS_CellUV_Flag == 0"),
        ])
        info = _req_info(
            signals=["BMS_CellUV_Flag"],
            requirement_description=(
                "IF any cell voltage reaches 2.80 V THEN BMS_CellUV_Flag := 1."
            ),
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "5.1.1" in failed

    def test_fails_when_strict_boundary_expects_trigger_at_exact_threshold(self):
        case = _case(steps=[
            _step(
                action="Set cell voltage to r_CellOV_Threshold",
                expected="BMS_CellOV_Detect := 1",
            ),
        ])
        info = _req_info(
            signals=["BMS_CellOV_Detect"],
            thresholds=["r_CellOV_Threshold"],
            requirement_description=(
                "IF any cell voltage exceeds r_CellOV_Threshold "
                "THEN BMS_CellOV_Detect := 1."
            ),
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "5.1.1" in failed

    def test_fails_when_case_expects_no_trigger_at_inclusive_timing_boundary(self):
        case = _case(steps=[
            _step(action="Set BMS_CellOV_Detect to 1", expected=None),
            _step(action="Wait for t_CellOV_Debounce", expected=None),
            _step(action="Check response", expected="BMS_CellOV_Flag == 0"),
        ])
        info = _req_info(
            signals=["BMS_CellOV_Detect", "BMS_CellOV_Flag"],
            timing=["t_CellOV_Debounce"],
            requirement_description=(
                "IF BMS_CellOV_Detect = 1 for a continuous duration >= "
                "t_CellOV_Debounce THEN BMS_CellOV_Flag := 1."
            ),
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "5.1.1" in failed

    def test_fails_when_natural_language_timing_boundary_expects_no_trigger(self):
        case = _case(steps=[
            _step(action="Set BMS_CellOV_Detect to 1", expected=None),
            _step(action="Wait for t_CellOV_Debounce", expected=None),
            _step(action="Check response", expected="BMS_CellOV_Flag == 0"),
        ])
        info = _req_info(
            signals=["BMS_CellOV_Detect", "BMS_CellOV_Flag"],
            timing=["t_CellOV_Debounce"],
            requirement_description=(
                "IF BMS_CellOV_Detect remains active for at least "
                "t_CellOV_Debounce THEN BMS_CellOV_Flag := 1."
            ),
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "5.1.1" in failed

    def test_fails_when_response_time_is_treated_as_debounce_no_trigger(self):
        case = _case(steps=[
            _step(action="Set pack charge current above 150 A", expected=None),
            _step(action="Wait shorter than 50 ms", expected="BMS_ChargeOC_Flag == 0"),
        ])
        info = _req_info(
            signals=["BMS_ChargeOC_Flag"],
            requirement_description=(
                "IF pack charge current exceeds 150 A THEN "
                "BMS_ChargeOC_Flag := 1 and limit charge current to "
                "100 A within 50 ms."
            ),
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "5.1.1" in failed

    def test_supplementary_calibration_range_does_not_authorize_endpoint_case(self):
        case = _case(steps=[
            _step(action="Set cell voltage to 4.15 V", expected="Cell voltage == 4.15 V"),
            _step(
                action="Wait raw detection response time [NEEDS REVIEW]",
                expected="BMS_CellOV_Detect := 1",
            ),
        ])
        info = _req_info(
            signals=["BMS_CellOV_Detect"],
            expected_missing_categories=["signal", "timing"],
            requirement_description=(
                "BMS_CellOV_Detect shall be set to 1 when any cell voltage "
                ">= r_CellOV_Threshold."
            ),
            supplementary_info=(
                "r_CellOV_Threshold: detection level [4.15 V - 4.35 V]"
            ),
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "2.2.1" in failed

    def test_explicit_accepted_test_basis_authorizes_numeric_endpoint(self):
        case = _case(steps=[
            _step(action="Set cell voltage to 4.15 V", expected="Cell voltage == 4.15 V"),
            _step(
                action="Wait raw detection response time [NEEDS REVIEW]",
                expected="BMS_CellOV_Detect := 1",
            ),
        ])
        info = _req_info(
            signals=["BMS_CellOV_Detect"],
            expected_missing_categories=["signal", "timing"],
            requirement_description=(
                "BMS_CellOV_Detect shall be set to 1 when any cell voltage "
                ">= r_CellOV_Threshold."
            ),
            supplementary_info=(
                "r_CellOV_Threshold: detection level [4.15 V - 4.35 V]"
            ),
            accepted_test_basis="For this calibration review, use 4.15 V.",
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "2.2.1" not in failed

    def test_allows_close_boundary_representative_value_from_requirement_threshold(self):
        case = _case(steps=[
            _step(action="Set cell voltage to 2.75 V", expected="BMS_CellUV_Flag == 0"),
        ])
        info = _req_info(
            signals=["BMS_CellUV_Flag"],
            requirement_description=(
                "IF any cell voltage <= 2.80 V THEN BMS_CellUV_Flag := 1."
            ),
        )

        failed, warnings = evaluate_case(case, info, {})

        assert "2.2.1" not in failed


# ── evaluate_missing_info_hard_gates ─────────────────────────────────────


class TestEvaluateMissingInfoHardGates:
    def _req_entry(self, key="REQ-001", bucket="test", expected=None,
                   actual_items=None, cases=None):
        return {
            "requirement_key": key,
            "evaluation_bucket": bucket,
            "expected_missing_categories": expected or [],
            "analysis": {
                "signals": [],
                "thresholds": [],
                "timing": [],
                "missing_info_items": actual_items or [],
            },
            "cases": cases or [],
        }

    def test_detects_missing_category(self):
        data = [self._req_entry(
            expected=["timing", "threshold"],
            actual_items=[],
        )]
        records = evaluate_missing_info_hard_gates(data)
        assert len(records) == 1
        assert set(records[0]["missing_from_actual"]) == {"timing", "threshold"}
        assert records[0]["matched"] == []

    def test_detects_extra_category(self):
        data = [self._req_entry(
            expected=["timing"],
            actual_items=[
                {"category": "timing", "description": "resp time missing"},
                {"category": "state", "description": "state not given"},
            ],
        )]
        records = evaluate_missing_info_hard_gates(data)
        assert records[0]["extra_in_actual"] == ["state"]
        assert records[0]["matched"] == ["timing"]

    def test_full_match(self):
        data = [self._req_entry(
            expected=["timing", "threshold"],
            actual_items=[
                {"category": "timing", "description": "resp time missing"},
                {"category": "threshold", "description": "OV threshold missing"},
            ],
        )]
        records = evaluate_missing_info_hard_gates(data)
        assert records[0]["missing_from_actual"] == []
        assert records[0]["extra_in_actual"] == []
        assert set(records[0]["matched"]) == {"timing", "threshold"}

    def test_case_missing_nr_when_expected_missing(self):
        data = [self._req_entry(
            expected=["timing"],
            actual_items=[{"category": "timing", "description": "resp time missing"}],
            cases=[_case(title="TC-01", steps=[
                _step(action="Wait 100ms", expected="Flag set"),
            ])],
        )]
        records = evaluate_missing_info_hard_gates(data)
        assert len(records[0]["case_issues"]) == 1
        assert "missing [NEEDS REVIEW]" in records[0]["case_issues"][0]["issue"]

    def test_skips_when_no_expected_missing(self):
        data = [self._req_entry(expected=[])]
        records = evaluate_missing_info_hard_gates(data)
        assert len(records) == 0

    def test_hard_gate_item_ids_when_missing(self):
        """3.2.1 assigned when LLM#1 misses expected categories."""
        data = [self._req_entry(
            expected=["timing", "threshold"],
            actual_items=[],
        )]
        records = evaluate_missing_info_hard_gates(data)
        assert "3.2.1" in records[0]["item_ids"]

    def test_case_issue_includes_item_id(self):
        """Case issue carries 3.2.1 when [NEEDS REVIEW] is missing."""
        data = [self._req_entry(
            expected=["timing"],
            actual_items=[{"category": "timing", "description": "resp time missing"}],
            cases=[_case(title="TC-01", steps=[
                _step(action="Wait 100ms", expected="Flag set"),
            ])],
        )]
        records = evaluate_missing_info_hard_gates(data)
        assert records[0]["case_issues"][0]["item_id"] == "3.2.1"

    def test_evaluate_case_returns_warnings_tuple(self):
        """evaluate_case returns (failed, warnings) tuple."""
        case = _case()
        result = evaluate_case(case, _req_info(), {})
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], list)
        assert isinstance(result[1], list)


# ── Report rendering ───────────────────────────────────────────────────


class TestReportRendering:
    def test_warning_items_in_report_html(self):
        """Warning items appear in the report HTML when triggered."""
        from collections import Counter
        from optimization.generate_report import _render_warning_items

        counts = Counter({"3.2.3": 3, "4.1.1": 1})
        html = _render_warning_items(counts, 50)
        assert "WARNING 检查项" in html
        assert "3.2.3" in html
        assert "4.1.1" in html
        assert "3" in html   # count for 3.2.3
        assert "WARNING" in html

    def test_warning_empty_when_no_warnings(self):
        from collections import Counter
        from optimization.generate_report import _render_warning_items

        html = _render_warning_items(Counter(), 50)
        assert html == ""

    def test_hard_gate_section_includes_item_ids(self):
        """Hard gate HTML table includes item_ids column with 3.2.1."""
        from optimization.generate_report import _render_hard_gate_section

        records = [{
            "requirement_key": "REQ-001",
            "evaluation_bucket": "test",
            "expected_missing_categories": ["timing"],
            "actual_missing_categories": [],
            "matched": [],
            "missing_from_actual": ["timing"],
            "extra_in_actual": [],
            "case_issues": [],
            "item_ids": ["3.2.1"],
        }]
        html = _render_hard_gate_section(records)
        assert "3.2.1" in html
        assert "Item IDs" in html
        assert "⚠️ LLM#1 遗漏" in html
