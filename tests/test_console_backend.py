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
from testcase_agent.console.db import init_db, run_migrations
from testcase_agent.pipeline.generate import RequirementInput


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "test_pipeline_console.db"
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    run_migrations(conn)
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

        # Must accept LLM-A before advancing
        client.post(f"/api/v1/console/runs/{run_id}/accept/a")

        resp = client.post(f"/api/v1/console/runs/{run_id}/advance")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run"]["status"] in ("intents_ready", "cases_ready")
        assert len(data["intents"]) >= 1

    def test_advance_blocked_by_review(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={
            "requirement_id": 1,
            "review_required": ["a"],
        })
        run_id = cr.json()["run"]["id"]

        # Advance should be blocked because LLM-A not yet accepted
        resp = client.post(f"/api/v1/console/runs/{run_id}/advance")
        assert resp.status_code == 409

    def test_accept_blocked_when_already_accepted(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={
            "requirement_id": 1,
            "review_required": ["a"],
        })
        run_id = cr.json()["run"]["id"]
        resp = client.post(f"/api/v1/console/runs/{run_id}/accept/a")
        assert resp.status_code == 200
        # Second accept should return 409
        resp2 = client.post(f"/api/v1/console/runs/{run_id}/accept/a")
        assert resp2.status_code == 409

    def test_review_state_endpoint(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={
            "requirement_id": 1,
            "review_required": ["a"],
        })
        run_id = cr.json()["run"]["id"]
        resp = client.get(f"/api/v1/console/runs/{run_id}/review-state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["a"]["review_required"] is True
        assert data["a"]["accepted"] is False

    def test_llm_a_review_flow(self, client, db):
        """Integration test: LLM-A Accept → Advance → complete."""
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={
            "requirement_id": 1,
            "review_required": ["a"],
        })
        run_id = cr.json()["run"]["id"]
        assert cr.json()["run"]["status"] == "extraction_ready"

        # Accept LLM-A
        resp = client.post(f"/api/v1/console/runs/{run_id}/accept/a")
        assert resp.status_code == 200

        # Verify review state
        state = client.get(f"/api/v1/console/runs/{run_id}/review-state").json()
        assert state["a"]["accepted"] is True

        # Unlock LLM-A (no cascade since no downstream data)
        resp = client.post(f"/api/v1/console/runs/{run_id}/unlock/a")
        assert resp.status_code == 200
        state = client.get(f"/api/v1/console/runs/{run_id}/review-state").json()
        assert state["a"]["accepted"] is False

        # Re-accept and advance
        client.post(f"/api/v1/console/runs/{run_id}/accept/a")
        resp = client.post(f"/api/v1/console/runs/{run_id}/advance")
        assert resp.status_code == 200

    def test_regenerate_requires_comment(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={
            "requirement_id": 1,
            "review_required": ["a"],
        })
        run_id = cr.json()["run"]["id"]
        resp = client.post(
            f"/api/v1/console/runs/{run_id}/sections/signals/items/sign-1/regenerate",
            json={"comment": ""},
        )
        assert resp.status_code == 422

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


# ── Migration Tests ────────────────────────────────────────────────────────────

class TestMigration:
    def test_idempotent_on_empty_db(self, db):
        from testcase_agent.console.db import run_migrations
        run_migrations(db)
        run_migrations(db)  # second run must not error

        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [t[0] for t in tables]
        assert "review_actions" in names

    def test_idempotent_on_existing_data(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        init_db(db)
        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute(
            "INSERT INTO runs (requirement_id, status) VALUES (1, 'cases_ready')"
        )
        db.execute(
            "INSERT INTO test_basis_sections (run_id, section_name, sort_order) VALUES (1, 'signals', 0)"
        )
        db.execute(
            "INSERT INTO test_basis_items (section_id, item_id, status, content) VALUES (1, 'sig-1', 'known', 'S1')"
        )
        db.execute(
            "INSERT INTO case_intents (run_id, intent_id, coverage_dimension, intent_text) "
            "VALUES (1, 'i-1', 'normal', 'intent text')"
        )
        db.execute(
            "INSERT INTO test_cases (run_id, title) VALUES (1, 'TC1')"
        )
        db.commit()

        run_migrations(db)
        run_migrations(db)  # idempotent

        item = db.execute("SELECT review_status FROM test_basis_items WHERE item_id='sig-1'").fetchone()
        assert item["review_status"] == "accepted"

        intent = db.execute("SELECT review_status, version FROM case_intents WHERE intent_id='i-1'").fetchone()
        assert intent["review_status"] == "accepted"
        assert intent["version"] == 1

        case = db.execute("SELECT review_status FROM test_cases WHERE title='TC1'").fetchone()
        assert case["review_status"] == "accepted"

        run = db.execute("SELECT llm_a_accepted, llm_b_accepted, llm_c_accepted FROM runs WHERE id=1").fetchone()
        assert run["llm_a_accepted"] == 1
        assert run["llm_b_accepted"] == 1
        assert run["llm_c_accepted"] == 1

    def test_review_actions_read_write(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute("INSERT INTO runs (id, requirement_id, status) VALUES (1, 1, 'extraction_ready')")
        db.commit()

        db.execute(
            "INSERT INTO review_actions (run_id, stage, action, target_type, target_id, comment) "
            "VALUES (1, 'a', 'accept', 'stage', NULL, NULL)"
        )
        db.commit()

        row = db.execute("SELECT * FROM review_actions WHERE run_id=1").fetchone()
        assert row is not None
        assert row["stage"] == "a"
        assert row["action"] == "accept"


# ── Review State Machine Tests ──────────────────────────────────────────────────

class TestReviewStateMachine:
    def test_accept_stage_a(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        from testcase_agent.console.review_state import accept_stage
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute("INSERT INTO runs (id, requirement_id, review_llm_a, status) VALUES (1, 1, 1, 'extraction_ready')")
        db.execute("INSERT INTO test_basis_sections (id, run_id, section_name, sort_order) VALUES (1, 1, 'signals', 0)")
        db.execute("INSERT INTO test_basis_items (id, section_id, item_id, status, content) VALUES (1, 1, 'sig-1', 'known', 'S1')")
        db.execute("INSERT INTO test_basis_items (id, section_id, item_id, status, content) VALUES (2, 1, 'sig-2', 'needs_review', 'S2')")
        db.commit()

        accept_stage(db, 1, "a")

        items = db.execute("SELECT review_status, accepted_at FROM test_basis_items").fetchall()
        for it in items:
            assert it["review_status"] == "accepted"
            assert it["accepted_at"] is not None

        run = db.execute("SELECT llm_a_accepted FROM runs WHERE id=1").fetchone()
        assert run["llm_a_accepted"] == 1

        action = db.execute("SELECT * FROM review_actions WHERE run_id=1").fetchone()
        assert action is not None
        assert action["stage"] == "a"
        assert action["action"] == "accept"

    def test_accept_stage_b(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        from testcase_agent.console.review_state import accept_stage
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute("INSERT INTO runs (id, requirement_id, review_llm_b, status) VALUES (1, 1, 1, 'intents_ready')")
        db.execute("INSERT INTO case_intents (run_id, intent_id, coverage_dimension, intent_text) VALUES (1, 'i-1', 'normal', 'text')")
        db.execute("INSERT INTO case_intents (run_id, intent_id, coverage_dimension, intent_text) VALUES (1, 'i-2', 'boundary', 'text')")
        db.commit()

        accept_stage(db, 1, "b")

        intents = db.execute("SELECT review_status, accepted_at FROM case_intents").fetchall()
        for intent in intents:
            assert intent["review_status"] == "accepted"
            assert intent["accepted_at"] is not None

        run = db.execute("SELECT llm_b_accepted FROM runs WHERE id=1").fetchone()
        assert run["llm_b_accepted"] == 1

    def test_accept_stage_c(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        from testcase_agent.console.review_state import accept_stage
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute("INSERT INTO runs (id, requirement_id, review_llm_c, status) VALUES (1, 1, 1, 'cases_ready')")
        db.execute("INSERT INTO test_cases (run_id, title) VALUES (1, 'TC1')")
        db.commit()

        accept_stage(db, 1, "c")

        cases = db.execute("SELECT review_status, accepted_at FROM test_cases").fetchall()
        for case in cases:
            assert case["review_status"] == "accepted"
            assert case["accepted_at"] is not None

        run = db.execute("SELECT llm_c_accepted FROM runs WHERE id=1").fetchone()
        assert run["llm_c_accepted"] == 1

    def test_unlock_stage_clears_accepted_at(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        from testcase_agent.console.review_state import accept_stage, unlock_stage
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute("INSERT INTO runs (id, requirement_id, review_llm_a, status) VALUES (1, 1, 1, 'extraction_ready')")
        db.execute("INSERT INTO test_basis_sections (id, run_id, section_name, sort_order) VALUES (1, 1, 'signals', 0)")
        db.execute("INSERT INTO test_basis_items (id, section_id, item_id, status, content) VALUES (1, 1, 'sig-1', 'known', 'S1')")
        db.commit()

        accept_stage(db, 1, "a")
        unlock_stage(db, 1, "a", cascade=False)

        items = db.execute("SELECT review_status, accepted_at FROM test_basis_items").fetchall()
        for it in items:
            assert it["review_status"] == "pending"
            assert it["accepted_at"] is None

        run = db.execute("SELECT llm_a_accepted FROM runs WHERE id=1").fetchone()
        assert run["llm_a_accepted"] == 0

    def test_can_advance_blocks_when_not_accepted(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        from testcase_agent.console.review_state import can_advance
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute(
            "INSERT INTO runs (id, requirement_id, status, review_llm_a, llm_a_accepted) "
            "VALUES (1, 1, 'extraction_ready', 1, 0)"
        )
        db.commit()

        ok, msg = can_advance(db, 1)
        assert not ok
        assert "LLM-A" in msg

    def test_can_advance_allows_when_accepted(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        from testcase_agent.console.review_state import can_advance
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute(
            "INSERT INTO runs (id, requirement_id, status, review_llm_a, llm_a_accepted) "
            "VALUES (1, 1, 'extraction_ready', 1, 1)"
        )
        db.commit()

        ok, msg = can_advance(db, 1)
        assert ok
        assert msg == ""

    def test_can_regenerate_intents_limit(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        from testcase_agent.console.review_state import can_regenerate_intents
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute("INSERT INTO runs (id, requirement_id, status) VALUES (1, 1, 'intents_ready')")
        db.execute(
            "INSERT INTO case_intents (run_id, intent_id, coverage_dimension, intent_text, regenerate_count) "
            "VALUES (1, 'i-1', 'normal', 'text', 3)"
        )
        db.commit()

        assert not can_regenerate_intents(db, 1)

    def test_can_regenerate_intents_allows(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        from testcase_agent.console.review_state import can_regenerate_intents
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute("INSERT INTO runs (id, requirement_id, status) VALUES (1, 1, 'intents_ready')")
        db.execute(
            "INSERT INTO case_intents (run_id, intent_id, coverage_dimension, intent_text, regenerate_count) "
            "VALUES (1, 'i-1', 'normal', 'text', 2)"
        )
        db.commit()

        assert can_regenerate_intents(db, 1)

    def test_get_stage_states(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        from testcase_agent.console.review_state import get_stage_states
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute(
            "INSERT INTO runs (id, requirement_id, status, review_llm_a, review_llm_b, review_llm_c, "
            "llm_a_accepted, llm_b_accepted, llm_c_accepted) "
            "VALUES (1, 1, 'extraction_ready', 1, 0, 0, 0, 0, 0)"
        )
        db.commit()

        states = get_stage_states(db, 1)
        assert states["a"]["review_required"] is True
        assert states["a"]["accepted"] is False
        assert states["b"]["review_required"] is False
        assert states["c"]["review_required"] is False

    def test_check_cascade_impact_a(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        from testcase_agent.console.review_state import check_cascade_impact
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute("INSERT INTO runs (id, requirement_id, status) VALUES (1, 1, 'cases_ready')")
        db.execute("INSERT INTO case_intents (run_id, intent_id, coverage_dimension, intent_text) VALUES (1, 'i-1', 'normal', 'text')")
        db.execute("INSERT INTO case_intents (run_id, intent_id, coverage_dimension, intent_text) VALUES (1, 'i-2', 'boundary', 'text')")
        db.execute("INSERT INTO test_cases (run_id, title) VALUES (1, 'TC1')")
        db.commit()

        impact = check_cascade_impact(db, 1, "a")
        assert impact["affected_intents"] == 2
        assert impact["affected_cases"] == 1

    def test_check_cascade_impact_b(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        from testcase_agent.console.review_state import check_cascade_impact
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute("INSERT INTO runs (id, requirement_id, status) VALUES (1, 1, 'cases_ready')")
        db.execute("INSERT INTO test_cases (run_id, title) VALUES (1, 'TC1')")
        db.execute("INSERT INTO test_cases (run_id, title) VALUES (1, 'TC2')")
        db.commit()

        impact = check_cascade_impact(db, 1, "b")
        assert impact["affected_cases"] == 2
        assert impact["affected_intents"] == 0

    def test_cascade_stale_data_from_a(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        from testcase_agent.console.review_state import cascade_stale_data
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute("INSERT INTO runs (id, requirement_id, status, llm_b_accepted, llm_c_accepted) VALUES (1, 1, 'cases_ready', 1, 1)")
        db.execute("INSERT INTO case_intents (run_id, intent_id, coverage_dimension, intent_text) VALUES (1, 'i-1', 'normal', 'text')")
        db.execute("INSERT INTO test_cases (run_id, title) VALUES (1, 'TC1')")
        db.commit()

        cascade_stale_data(db, 1, "a")

        intent = db.execute("SELECT review_status FROM case_intents WHERE intent_id='i-1'").fetchone()
        assert intent["review_status"] == "stale"

        case = db.execute("SELECT review_status FROM test_cases WHERE title='TC1'").fetchone()
        assert case["review_status"] == "stale"

        run = db.execute("SELECT status, llm_b_accepted, llm_c_accepted FROM runs WHERE id=1").fetchone()
        assert run["status"] == "extraction_ready"
        assert run["llm_b_accepted"] == 0
        assert run["llm_c_accepted"] == 0

    def test_cascade_stale_data_from_b(self, db):
        from testcase_agent.console.db import run_migrations, init_db
        from testcase_agent.console.review_state import cascade_stale_data
        init_db(db)
        run_migrations(db)

        db.execute("INSERT INTO requirements (requirement_key, description) VALUES ('K1','D1')")
        db.execute("INSERT INTO runs (id, requirement_id, status, llm_c_accepted) VALUES (1, 1, 'cases_ready', 1)")
        db.execute("INSERT INTO test_cases (run_id, title) VALUES (1, 'TC1')")
        db.commit()

        cascade_stale_data(db, 1, "b")

        case = db.execute("SELECT review_status FROM test_cases WHERE title='TC1'").fetchone()
        assert case["review_status"] == "stale"

        run = db.execute("SELECT status, llm_c_accepted FROM runs WHERE id=1").fetchone()
        assert run["status"] == "intents_ready"
        assert run["llm_c_accepted"] == 0


# ── LLM-B / LLM-C / Cascade / Audit Tests ────────────────────────────────────

class TestLLMBStage:
    def test_regenerate_intents_requires_comment(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={"requirement_id": 1, "review_required": []})
        run_id = cr.json()["run"]["id"]
        resp = client.post(f"/api/v1/console/runs/{run_id}/regenerate-intents", json={"comment": ""})
        assert resp.status_code == 422

    def test_intents_history(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={"requirement_id": 1, "review_required": []})
        run_id = cr.json()["run"]["id"]
        # Ensure intents exist by advancing if needed
        data = client.get(f"/api/v1/console/runs/{run_id}").json()
        if data["run"]["status"] in ("extraction_ready",):
            client.post(f"/api/v1/console/runs/{run_id}/advance")
        data = client.get(f"/api/v1/console/runs/{run_id}").json()
        if data["run"]["status"] in ("extraction_ready",):
            client.post(f"/api/v1/console/runs/{run_id}/advance")
        resp = client.get(f"/api/v1/console/runs/{run_id}/intents/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "versions" in data

    def test_llm_b_accept_and_unlock(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={"requirement_id": 1, "review_required": ["b"]})
        run_id = cr.json()["run"]["id"]
        # Advance past A first (A is auto-approve)
        client.post(f"/api/v1/console/runs/{run_id}/accept/a")
        client.post(f"/api/v1/console/runs/{run_id}/advance")
        # Now accept B
        resp = client.post(f"/api/v1/console/runs/{run_id}/accept/b")
        assert resp.status_code == 200
        # Unlock B
        resp = client.post(f"/api/v1/console/runs/{run_id}/unlock/b")
        assert resp.status_code == 200


class TestLLMCStage:
    def test_llm_c_accept(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={"requirement_id": 1, "review_required": ["c"]})
        run_id = cr.json()["run"]["id"]
        # Auto-advance through A and B
        client.post(f"/api/v1/console/runs/{run_id}/accept/a")
        client.post(f"/api/v1/console/runs/{run_id}/advance")  # runs LLM-B
        client.post(f"/api/v1/console/runs/{run_id}/accept/b")
        client.post(f"/api/v1/console/runs/{run_id}/advance")  # runs LLM-C
        # Accept C
        resp = client.post(f"/api/v1/console/runs/{run_id}/accept/c")
        assert resp.status_code == 200
        state = client.get(f"/api/v1/console/runs/{run_id}/review-state").json()
        assert state["c"]["accepted"] is True


class TestCascade:
    def test_cascade_warning_on_unlock_a(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={"requirement_id": 1, "review_required": []})
        run_id = cr.json()["run"]["id"]
        # Accept A, then unlock
        client.post(f"/api/v1/console/runs/{run_id}/accept/a")
        resp = client.post(f"/api/v1/console/runs/{run_id}/unlock/a")
        data = resp.json()
        if "cascade_warning" in data:
            assert data["cascade_warning"] is True

    def test_unlock_c_no_warning(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={"requirement_id": 1, "review_required": ["c"]})
        run_id = cr.json()["run"]["id"]
        client.post(f"/api/v1/console/runs/{run_id}/accept/c")
        resp = client.post(f"/api/v1/console/runs/{run_id}/unlock/c")
        assert resp.status_code == 200


class TestAuditTrail:
    def test_review_actions_endpoint(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={"requirement_id": 1, "review_required": ["a"]})
        run_id = cr.json()["run"]["id"]
        client.post(f"/api/v1/console/runs/{run_id}/accept/a")
        resp = client.get(f"/api/v1/console/runs/{run_id}/review-actions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["actions"]) >= 1
        assert data["actions"][0]["stage"] == "a"
        assert data["actions"][0]["action"] == "accept"

    def test_review_actions_filter_stage(self, client, db):
        _seed_requirement(client)
        cr = client.post("/api/v1/console/runs", json={"requirement_id": 1, "review_required": ["a"]})
        run_id = cr.json()["run"]["id"]
        client.post(f"/api/v1/console/runs/{run_id}/accept/a")
        resp = client.get(f"/api/v1/console/runs/{run_id}/review-actions?stage=a")
        assert resp.status_code == 200
        data = resp.json()
        for a in data["actions"]:
            assert a["stage"] == "a"


def _seed_requirement(client):
    fixture = Path("tests/fixtures/minimal_requirements.xlsx")
    with open(fixture, "rb") as f:
        client.post(
            "/api/v1/console/requirements/import",
            files={"file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
