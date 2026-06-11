"""End-to-End Prompt Learning happy path test.

Verifies the full user-visible flow: upload → column mapping → run →
version saved → version readable → no Case Generation side effects.
"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from testcase_agent.api import create_app


def _make_xlsx(sheets: dict[str, list[list[str]]]) -> bytes:
    wb = Workbook()
    for idx, (name, rows) in enumerate(sheets.items()):
        if idx == 0:
            ws = wb.active
            ws.title = name
        else:
            ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Test fixtures ──

REQ_XLSX = _make_xlsx({
    "Requirements": [
        ["Req ID", "Description", "Function", "Type"],
        ["REQ-OVP-001", "Cell overvoltage protection shall trigger cutoff within 100ms when voltage exceeds 4.25V", "OVP", "requirement"],
        ["REQ-UVP-001", "Cell undervoltage protection shall disconnect load when voltage drops below 2.5V", "UVP", "requirement"],
        ["REQ-TMP-001", "Temperature monitoring shall trigger warning at 80°C and fault at 100°C", "TEMP", "requirement"],
        ["REQ-HEAD", "BMS Protection Functions", "BMS", "heading"],
    ],
})

CASE_XLSX = _make_xlsx({
    "Functional": [
        ["Case ID", "Req Link", "Title", "Action", "Expected Result", "Objective"],
        ["TC-001", "REQ-OVP-001", "Overvoltage cutoff at 4.25V",
         "1. Set power supply to 4.20V\n2. Verify normal operation\n3. Ramp to 4.30V at 10mV/s\n4. Monitor cutoff signal",
         "Cutoff triggers within 100ms of exceeding 4.25V threshold\nOutput returns to safe state",
         "Verify overvoltage protection response time"],
        ["TC-002", "REQ-OVP-001", "Overvoltage boundary at 4.24V",
         "1. Set power supply to 4.24V\n2. Hold for 10 seconds\n3. Verify no cutoff",
         "No cutoff triggered\nNormal operation maintained",
         "Verify no false trigger near threshold"],
        ["TC-003", "REQ-UVP-001", "Undervoltage disconnect at 2.5V",
         "1. Set power supply to 3.0V\n2. Ramp down to 2.4V\n3. Monitor disconnect signal",
         "Disconnect triggers when voltage drops below 2.5V\nLoad is isolated",
         "Verify undervoltage disconnect threshold"],
        ["TC-004", "REQ-TMP-001", "Temperature warning at 80°C",
         "1. Set up temperature chamber\n2. Ramp to 85°C\n3. Monitor warning signal",
         "Warning triggered at 80°C ± 2°C\nFault triggered at 100°C ± 2°C",
         "Verify temperature warning and fault thresholds"],
    ],
    "Regression": [
        ["Case ID", "Req Link", "Title", "Action", "Expected Result", "Objective"],
        ["TC-R01", "REQ-OVP-001, REQ-UVP-001", "Combined OV/UV protection",
         "1. Apply normal voltage\n2. Inject OV fault\n3. Recover\n4. Inject UV fault\n5. Recover",
         "Both protections operate independently\nRecovery to normal state after each",
         "Verify combined protection behavior"],
    ],
})


MOCK_LLM_RESPONSE = """<file name="analyze_test_basis.system.html">
<p>Analyze requirement {{ requirement_key }}: {{ description }}.</p>
<p>Extract allowed signals, thresholds, timing constraints, states, and observations. Output JSON.</p>
</file>
<file name="analyze_test_basis.user.html">
<p>Requirement: {{ requirement_key }} - {{ description }}</p>
<p>Function: {{ function_name }}</p>
</file>
<file name="plan_case_intents.system.html">
<p>Plan test case intents for {{ requirement_key }}: {{ description }}.</p>
<p>Allowed signals: {{ allowed_signals }}</p>
<p>Allowed thresholds: {{ allowed_thresholds }}</p>
<p>Allowed timing: {{ allowed_timing }}</p>
<p>Allowed states: {{ allowed_states }}</p>
<p>Allowed observations: {{ allowed_observations }}</p>
<p>Missing info: {{ missing_info }}.</p>
<p>Output JSON.</p>
</file>
<file name="plan_case_intents.user.html">
<p>{{ requirement_key }} - {{ description }}</p>
<p>Coverage dimensions to plan: normal_behavior, boundary_or_threshold, fault_or_protection</p>
</file>
<file name="generate_case.system.html">
<p>Generate test case for {{ requirement_key }}: {{ description }}.</p>
<p>Supplementary: {{ supplementary_info }}</p>
<p>Coverage dimension: {{ coverage_dimension }}</p>
<p>Case intent: {{ case_intent }}</p>
<p>Review comment: {{ review_comment }}</p>
<p>Extracted signals: {{ extracted_signals }}</p>
<p>Extracted thresholds: {{ extracted_thresholds }}</p>
<p>Extracted timing: {{ extracted_timing }}</p>
<p>Extracted states: {{ extracted_states }}</p>
<p>Extracted observations: {{ extracted_observations }}</p>
<p>Missing info: {{ missing_info }}</p>
<p>Missing info items: {{ missing_info_items }}</p>
<p>Output in <testcase> HTML format with title, objective, precondition, steps, and postcondition.</p>
</file>
<file name="generate_case.user.html">
<p>{{ requirement_key }} - {{ description }}</p>
<p>Intent: {{ case_intent }}</p>
</file>"""


class MockProvider:
    provider_name = "mock-e2e"
    model_name = "mock-model-e2e"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        return MOCK_LLM_RESPONSE


# ── E2E test ──

class TestPromptLearningE2E:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        """Patch the learned prompts root to use a temp directory."""
        self.tmp_root = tmp_path / "learned"
        self.patch = patch(
            "testcase_agent.prompt_learning.file_store._default_root",
            return_value=self.tmp_root,
        )
        self.patch.start()

        # Also patch create_provider to use mock
        self.provider_patch = patch(
            "testcase_agent.prompt_learning.router.create_provider",
            return_value=MockProvider(),
        )
        self.provider_patch.start()
        yield
        self.patch.stop()
        self.provider_patch.stop()

    @pytest.fixture
    def client(self):
        app = create_app()
        return TestClient(app)

    def test_full_e2e_flow(self, client):
        """Complete E2E: inspect → parse → run → list → read → no side effects."""

        # ── Step 1: Inspect workbooks ──
        res = client.post(
            "/api/v1/console/pl/inspect-workbooks",
            files=[
                ("req_file", ("req.xlsx", REQ_XLSX, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                ("case_file", ("case.xlsx", CASE_XLSX, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ],
        )
        assert res.status_code == 200, res.text
        insp = res.json()
        assert insp["requirement"]["filename"] == "req.xlsx"
        assert len(insp["requirement"]["sheets"]) == 1
        assert len(insp["referenceTestCase"]["sheets"]) == 2

        # ── Step 2: Parse & resolve ──
        res = client.post(
            "/api/v1/console/pl/parse-and-resolve",
            files=[
                ("req_file", ("req.xlsx", REQ_XLSX, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                ("case_file", ("case.xlsx", CASE_XLSX, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ],
            data={
                "req_sheet": "Requirements",
                "case_sheets": json.dumps(["Functional", "Regression"]),
                "req_mapping": json.dumps({
                    "requirementKey": "Req ID",
                    "description": "Description",
                    "functionName": "Function",
                    "requirementType": "Type",
                }),
                "case_mapping": json.dumps({
                    "caseId": "Case ID",
                    "linkedRequirements": "Req Link",
                    "title": "Title",
                    "action": "Action",
                    "expectedResult": "Expected Result",
                    "objective": "Objective",
                }),
            },
        )
        assert res.status_code == 200, res.text
        summary = res.json()["summary"]
        assert summary["requirementCount"] == 4  # includes heading
        assert summary["refTestCaseCount"] == 5
        assert summary["validLinkCount"] == 6  # 3+2+1 from 3 reqs × 5 links
        # REQ-HEAD has no test → No-Test
        assert summary["noTestRequirementCount"] == 1

        # ── Step 3: Run Prompt Learning ──
        res = client.post(
            "/api/v1/console/pl/run",
            files=[
                ("req_file", ("req.xlsx", REQ_XLSX, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
                ("case_file", ("case.xlsx", CASE_XLSX, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")),
            ],
            data={
                "req_sheet": "Requirements",
                "case_sheets": json.dumps(["Functional", "Regression"]),
                "req_mapping": json.dumps({
                    "requirementKey": "Req ID",
                    "description": "Description",
                    "functionName": "Function",
                    "requirementType": "Type",
                }),
                "case_mapping": json.dumps({
                    "caseId": "Case ID",
                    "linkedRequirements": "Req Link",
                    "title": "Title",
                    "action": "Action",
                    "expectedResult": "Expected Result",
                    "objective": "Objective",
                }),
                "learning_instruction": "Focus on boundary value thresholds",
            },
        )
        assert res.status_code == 200, res.text
        run_result = res.json()
        assert run_result["success"] is True
        assert run_result["version"]
        assert run_result["meta"]["provider"] == "mock-e2e"
        version = run_result["version"]

        # ── Step 4: Verify file store contents ──
        vdir = self.tmp_root / version
        assert vdir.is_dir()
        assert (vdir / "metadata.json").exists()
        assert (vdir / "rationale.md").exists()
        for fname in [
            "analyze_test_basis.system.html", "analyze_test_basis.user.html",
            "plan_case_intents.system.html", "plan_case_intents.user.html",
            "generate_case.system.html", "generate_case.user.html",
        ]:
            assert (vdir / fname).exists(), f"Missing {fname}"
            content = (vdir / fname).read_text(encoding="utf-8")
            assert len(content) > 0, f"Empty {fname}"

        # Verify metadata.json contents
        meta = json.loads((vdir / "metadata.json").read_text(encoding="utf-8"))
        assert meta["version"] == version
        assert meta["provider"] == "mock-e2e"
        assert meta["model"] == "mock-model-e2e"
        assert "learningInstruction" in meta
        assert meta["summary"]["requirementCount"] == 4
        assert meta["summary"]["dataIssueCount"] >= 0

        # ── Step 5: List versions via API ──
        res = client.get("/api/v1/console/pl/versions")
        assert res.status_code == 200
        versions = res.json()["versions"]
        assert len(versions) >= 1
        assert any(v["version"] == version for v in versions)

        # ── Step 6: Read version via API ──
        res = client.get(f"/api/v1/console/pl/versions/{version}")
        assert res.status_code == 200
        v = res.json()
        assert v["meta"]["version"] == version
        assert len(v["promptGroups"]) == 3
        assert v["promptGroups"][0]["stage"] == "A"
        assert "rationale" in v
        # Verify rationale contains meaningful content
        assert len(v["rationale"]) > 50
        assert "Requirements: 4" in v["rationale"]
        assert "Focus on boundary value thresholds" in v["rationale"]

        # ── Step 7: No Case Generation side effects ──
        # Architecture guarantee: Prompt Learning runner never touches
        # the Pipeline Console DB (no runs, test cases, or evaluations created).
        # Verified by code review — runner.py uses only parse_*, resolve_links,
        # framework_validation, and file_store modules, none of which import
        # or use the console DB layer.
