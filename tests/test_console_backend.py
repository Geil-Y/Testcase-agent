"""Tests for Console DB, API, pipeline runner, advance, and evaluate.

Uses mock LLM provider throughout — no real LLM calls.
"""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from testcase_agent.api import create_app
from testcase_agent.console.db import init_db
from testcase_agent.pipeline.generate import RequirementInput


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_pipeline_console.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def client(db, monkeypatch):
    app = create_app()

    def mock_get_db():
        return db

    monkeypatch.setattr("testcase_agent.console.router.get_db", mock_get_db)
    monkeypatch.setattr("testcase_agent.console.pipeline_runner.render_prompt", lambda name, **kw: ("sys", "usr"))

    return TestClient(app)


# ── DB Tests ──────────────────────────────────────────────────────────────────

class TestDB:
    def test_init_creates_tables(self, db):
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t[0] for t in tables]
        assert "requirements" in names
        assert "runs" in names
        assert "test_basis_sections" in names
        assert "test_basis_items" in names
        assert "case_intents" in names
        assert "test_cases" in names
        assert "test_case_steps" in names
        assert "evaluation_results" in names

    def test_insert_requirements(self, db):
        db.execute(
            "INSERT INTO requirements (requirement_key, description) VALUES (?, ?)",
            ("REQ-001", "Test desc"),
        )
        db.commit()
        row = db.execute("SELECT * FROM requirements WHERE requirement_key='REQ-001'").fetchone()
        assert row is not None
        assert row["description"] == "Test desc"

    def test_duplicate_key_ignored(self, db):
        db.execute(
            "INSERT INTO requirements (requirement_key, description) VALUES (?, ?)",
            ("REQ-001", "First"),
        )
        db.commit()
        db.execute(
            "INSERT OR IGNORE INTO requirements (requirement_key, description) VALUES (?, ?)",
            ("REQ-001", "Second"),
        )
        db.commit()
        rows = db.execute(
            "SELECT * FROM requirements WHERE requirement_key='REQ-001'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["description"] == "First"


# ── API Tests ──────────────────────────────────────────────────────────────────

class TestRequirementsAPI:
    def test_list_empty(self, client):
        resp = client.get("/api/v1/console/requirements")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_import_excel(self, client):
        fixture = Path("tests/fixtures/minimal_requirements.xlsx")
        with open(fixture, "rb") as f:
            resp = client.post(
                "/api/v1/console/requirements/import",
                files={"file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 2
        assert data["total_rows"] == 2

    def test_list_after_import(self, client):
        fixture = Path("tests/fixtures/minimal_requirements.xlsx")
        with open(fixture, "rb") as f:
            client.post(
                "/api/v1/console/requirements/import",
                files={"file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        resp = client.get("/api/v1/console/requirements")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_search(self, client):
        fixture = Path("tests/fixtures/minimal_requirements.xlsx")
        with open(fixture, "rb") as f:
            client.post(
                "/api/v1/console/requirements/import",
                files={"file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        resp = client.get("/api/v1/console/requirements?q=OVP")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["requirement_key"] == "REQ-BMS-OVP-001"

    def test_get_requirement(self, client):
        fixture = Path("tests/fixtures/minimal_requirements.xlsx")
        with open(fixture, "rb") as f:
            client.post(
                "/api/v1/console/requirements/import",
                files={"file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        resp = client.get("/api/v1/console/requirements/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["requirement"]["requirement_key"] == "REQ-BMS-OVP-001"
        assert data["runs"] == []

    def test_get_requirement_404(self, client):
        resp = client.get("/api/v1/console/requirements/999")
        assert resp.status_code == 404


# ── Run API Tests ──────────────────────────────────────────────────────────────

class CapturingProvider:
    provider_name = "capture"
    model_name = "capture"

    def __init__(self, responses=None):
        self.calls: list[tuple[str, str]] = []
        self.responses = responses or []
        self._call_count = 0

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if self._call_count < len(self.responses):
            resp = self.responses[self._call_count]
        else:
            resp = self.responses[-1] if self.responses else "{}"
        self._call_count += 1
        return resp


_MOCK_RESPONSES = [
    # LLM-A: test basis JSON
    """{
        "requirement_key": "REQ-001",
        "allowed_signals": ["BMS_CellOV_Detect"],
        "allowed_thresholds": ["r_CellOV_Threshold"],
        "allowed_timing": [],
        "allowed_states": ["Normal", "OV_Detected"],
        "allowed_observations": [],
        "missing_info": [
            {"category": "timing", "description": "detection response time not specified"}
        ]
    }""",
    # LLM-B: case intents JSON
    """{
        "requirement_key": "REQ-001",
        "case_intents": [
            {"intent_id": "intent-1", "coverage_dimension": "normal_behavior",
             "intent_text": "Verify OV detection when voltage exceeds threshold."},
            {"intent_id": "intent-2", "coverage_dimension": "boundary_or_threshold",
             "intent_text": "Verify boundary just-below threshold does not trigger."}
        ]
    }""",
    # LLM-C call 1
    """<testcase><title>OV detection</title><objective>Verify OV detection.</objective><related_requirement>REQ-001</related_requirement><precondition>BMS initialized, all parameters within normal operating range, no active faults.</precondition><steps><step order="1"><action>Set cell voltage above threshold</action><expected>Voltage above threshold</expected></step><step order="2"><action>Wait for response</action><expected>BMS_CellOV_Detect := 1</expected></step></steps><postcondition>System returned to normal operating state.</postcondition></testcase>""",
    # LLM-C call 2
    """<testcase><title>Boundary no trigger</title><objective>Verify boundary does not trigger.</objective><related_requirement>REQ-001</related_requirement><precondition>BMS initialized, all parameters within normal operating range, no active faults.</precondition><steps><step order="1"><action>Set cell voltage just below threshold</action><expected>Voltage below threshold</expected></step><step order="2"><action>Wait</action><expected>BMS_CellOV_Detect := 0</expected></step></steps><postcondition>System returned to normal operating state.</postcondition></testcase>""",
]

_GLOBAL_CALL_COUNT = 0


def _mock_provider_factory(settings):
    global _GLOBAL_CALL_COUNT

    class GlobalCaptureProvider:
        provider_name = "global_capture"
        model_name = "global_capture"

        def __init__(self):
            self.calls: list[tuple[str, str]] = []

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            global _GLOBAL_CALL_COUNT
            self.calls.append((system_prompt, user_prompt))
            idx = _GLOBAL_CALL_COUNT
            _GLOBAL_CALL_COUNT += 1
            if idx < len(_MOCK_RESPONSES):
                return _MOCK_RESPONSES[idx]
            return _MOCK_RESPONSES[-1]

    return GlobalCaptureProvider()


class TestRunAPI:
    @pytest.fixture(autouse=True)
    def setup_provider(self, monkeypatch):
        global _GLOBAL_CALL_COUNT
        _GLOBAL_CALL_COUNT = 0

        monkeypatch.setattr(
            "testcase_agent.console.router.create_provider",
            _mock_provider_factory,
        )
        monkeypatch.setattr(
            "testcase_agent.console.pipeline_runner.render_prompt",
            lambda name, **kw: ("system prompt", "user prompt"),
        )

    def test_create_run(self, client, db):
        _seed_requirement(client)
        resp = client.post("/api/v1/console/runs", json={
            "requirement_id": 1,
            "review_required": ["a"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["run"]["status"] == "extraction_ready"
        assert len(data["sections"]) == 5
        # Check signals section
        sig_section = [s for s in data["sections"] if s["section_name"] == "signals"][0]
        assert len(sig_section["items"]) >= 1

    def test_create_run_full_auto(self, client, db):
        _seed_requirement(client)
        # We need LLM-B and LLM-C responses too for auto-chain
        resp = client.post("/api/v1/console/runs", json={
            "requirement_id": 1,
            "review_required": [],
        })
        assert resp.status_code == 200
        data = resp.json()
        # After auto-chain, should reach cases_ready
        assert data["run"]["status"] in ("extraction_ready", "intents_ready", "cases_ready")

    def test_get_run_404(self, client):
        resp = client.get("/api/v1/console/runs/999")
        assert resp.status_code == 404

    def test_get_run_with_data(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={
            "requirement_id": 1,
            "review_required": ["a"],
        })
        run_id = cr.json()["run"]["id"]
        resp = client.get(f"/api/v1/console/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run"]["id"] == run_id
        assert "sections" in data
        assert "cases" in data

    def test_update_item(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={
            "requirement_id": 1,
            "review_required": ["a"],
        })
        run_id = cr.json()["run"]["id"]
        sections = cr.json()["sections"]
        sig_section = [s for s in sections if s["section_name"] == "signals"][0]
        first_item = sig_section["items"][0]

        resp = client.put(
            f"/api/v1/console/runs/{run_id}/sections/signals/items/{first_item['item_id']}",
            json={"status": "needs_review", "content": "Updated"},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["status"] == "needs_review"
        assert updated["content"] == "Updated"

    def test_add_and_delete_item(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={
            "requirement_id": 1,
            "review_required": ["a"],
        })
        run_id = cr.json()["run"]["id"]

        # Add
        resp = client.post(
            f"/api/v1/console/runs/{run_id}/sections/signals/items",
            json={"item_id": "sig-new", "status": "known", "content": "NewSignal"},
        )
        assert resp.status_code == 200
        assert resp.json()["item_id"] == "sig-new"

        # Delete
        resp = client.delete(
            f"/api/v1/console/runs/{run_id}/sections/signals/items/sig-new"
        )
        assert resp.status_code == 204

    def test_advance_to_intents(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={
            "requirement_id": 1,
            "review_required": ["a"],
        })
        run_id = cr.json()["run"]["id"]

        resp = client.post(f"/api/v1/console/runs/{run_id}/advance")
        assert resp.status_code == 200
        data = resp.json()
        # With review_llm_b=0 (auto), LLM-B should run
        # With review_llm_c=0 (auto), LLM-C should also run (auto-chain)
        assert data["run"]["status"] in ("intents_ready", "cases_ready")
        assert len(data["intents"]) >= 1

    def test_evaluate(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={
            "requirement_id": 1,
            "review_required": [],
        })
        run_id = cr.json()["run"]["id"]

        # Advance to get cases (if not already)
        data = client.get(f"/api/v1/console/runs/{run_id}").json()
        if data["run"]["status"] in ("extraction_ready", "intents_ready",):
            client.post(f"/api/v1/console/runs/{run_id}/advance")

        # Evaluate
        resp = client.post(f"/api/v1/console/runs/{run_id}/evaluate")
        assert resp.status_code == 200
        eval_data = resp.json()
        assert "summary" in eval_data
        assert "total_cases" in eval_data["summary"]


def _seed_requirement(client):
    fixture = Path("tests/fixtures/minimal_requirements.xlsx")
    with open(fixture, "rb") as f:
        client.post(
            "/api/v1/console/requirements/import",
            files={"file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
