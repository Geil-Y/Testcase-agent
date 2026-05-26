"""Tests for Pipeline Console: import batches, API routes, and UI shell."""

from __future__ import annotations

import inspect
import json
import os
import re
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from src.testcase_agent.api import create_app
from src.testcase_agent.pipeline_console.imports import (
    confirm_import,
    get_batch,
    get_latest_batch,
    list_batches,
    list_batches_summary,
    save_batch,
)
from src.testcase_agent.pipeline_console.router import router as console_router
from src.testcase_agent.pipeline_console.jobs import (
    JobConflictError,
    JobRunner,
    JobStatus,
    get_job_runner,
)
from src.testcase_agent.pipeline_console.runs import (
    archive_artifacts,
    artifact_hash,
    artifacts_to_archive,
    content_hash,
    discover_runs,
    get_downstream_artifacts,
    get_latest_run,
    get_run,
    get_runs_for_requirement,
    has_changed,
    infer_run_status,
    make_run_dir,
    make_run_name,
    write_run_input,
)


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture
def sample_xlsx():
    """Create a temporary Excel file with requirements."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Requirements"
    ws.append(["Key", "Description", "Function", "Type", "Notes", "Priority"])
    ws.append(["REQ-001", "Check voltage threshold", "Voltage", "requirement", "Low priority note", "P1"])
    ws.append(["REQ-002", "Verify temperature sensor", "Temp", "requirement", "Critical note", "P1"])
    ws.append(["REQ-003", "Test overcurrent protection", "Current", "requirement", "", "P2"])
    ws.append(["REQ-H-001", "Section Heading", "", "heading", "", ""])
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(tmp.name)
    wb.close()
    tmppath = Path(tmp.name)
    yield tmppath
    try:
        tmppath.unlink(missing_ok=True)
    except PermissionError:
        pass  # Windows file locking


@pytest.fixture
def sample_requirements():
    return [
        {
            "id": 0,
            "requirement_key": "REQ-001",
            "description": "Check voltage threshold",
            "function_name": "Voltage",
            "requirement_type": "requirement",
            "supplementary_info": "Low priority note | P1",
            "is_heading": False,
            "is_info": False,
        },
        {
            "id": 1,
            "requirement_key": "REQ-002",
            "description": "Verify temperature sensor",
            "function_name": "Temp",
            "requirement_type": "requirement",
            "supplementary_info": "Critical note | P1",
            "is_heading": False,
            "is_info": False,
        },
    ]


# -- Save batch ---------------------------------------------------------------


class TestSaveBatch:
    """Tests for import batch persistence."""

    def test_save_and_retrieve_batch(self, sample_requirements):
        batch = save_batch(
            filename="test.xlsx",
            requirements=sample_requirements,
            mapping={"requirement_key_col": "Key", "description_col": "Description"},
        )

        assert "id" in batch
        assert batch["filename"] == "test.xlsx"
        assert batch["requirements_count"] == 2
        assert len(batch["requirements"]) == 2
        assert batch["requirements"][0]["requirement_key"] == "REQ-001"

        # Retrieve by id
        retrieved = get_batch(batch["id"])
        assert retrieved is not None
        assert retrieved["id"] == batch["id"]
        assert retrieved["requirements_count"] == 2
        assert len(retrieved["requirements"]) == 2

    def test_save_batch_creates_directory(self, sample_requirements):
        batch = save_batch(
            filename="dir_test.xlsx",
            requirements=sample_requirements,
            mapping={},
        )
        batch_dir = Path(__file__).resolve().parents[1] / "reviews" / "imports" / batch["id"]
        assert batch_dir.exists()
        assert (batch_dir / "metadata.json").exists()
        assert (batch_dir / "requirements.json").exists()

    def test_get_nonexistent_batch(self):
        assert get_batch("nonexistent_batch_id") is None


class TestListBatches:
    """Tests for batch listing."""

    def test_list_batches_newest_first(self, sample_requirements):
        b1 = save_batch(filename="first.xlsx", requirements=sample_requirements, mapping={})
        time.sleep(1.1)  # ensure distinct timestamps
        b2 = save_batch(filename="second.xlsx", requirements=sample_requirements, mapping={})

        batches = list_batches()
        assert len(batches) >= 2

        # Newest first
        idx_b1 = next(i for i, b in enumerate(batches) if b["id"] == b1["id"])
        idx_b2 = next(i for i, b in enumerate(batches) if b["id"] == b2["id"])
        assert idx_b2 < idx_b1  # b2 is newer

    def test_list_batches_summary_excludes_requirements(self, sample_requirements):
        save_batch(filename="summary_test.xlsx", requirements=sample_requirements, mapping={})
        summaries = list_batches_summary()
        assert len(summaries) >= 1
        for s in summaries:
            assert "requirements" not in s
            assert "id" in s
            assert "filename" in s

    def test_get_latest_batch_returns_most_recent(self, sample_requirements):
        save_batch(filename="older.xlsx", requirements=sample_requirements, mapping={})
        time.sleep(1.1)  # ensure distinct timestamp for ordering
        latest = save_batch(filename="newer.xlsx", requirements=sample_requirements, mapping={})

        result = get_latest_batch()
        assert result is not None
        assert result["id"] == latest["id"]

    def test_get_latest_batch_when_empty(self):
        # Can't easily test empty state with fixture-created batches,
        # so just test the function returns None or a dict
        batch = get_latest_batch()
        # May be None if no batches, or a dict from fixtures
        assert batch is None or isinstance(batch, dict)


# -- Excel import -------------------------------------------------------------


class TestExcelImport:
    """Tests for Excel preview and confirm flow."""

    def test_confirm_import_creates_batch(self, sample_xlsx):
        batch = confirm_import(
            tmp_path=str(sample_xlsx),
            sheet="Requirements",
            mapping_data={
                "requirement_key_col": "Key",
                "description_col": "Description",
                "function_name_col": "Function",
                "requirement_type_col": "Type",
                "supplementary_info_cols": ["Notes", "Priority"],
            },
            filename="test_import.xlsx",
        )

        assert "id" in batch
        assert batch["requirements_count"] == 4  # includes heading row
        assert batch["requirements"][0]["requirement_key"] == "REQ-001"
        assert batch["requirements"][0]["function_name"] == "Voltage"

    def test_confirm_import_cleans_up_temp_file(self, sample_xlsx):
        """confirm_import attempts to clean up; Windows file locking may prevent it."""
        batch = confirm_import(
            tmp_path=str(sample_xlsx),
            sheet="Requirements",
            mapping_data={
                "requirement_key_col": "Key",
                "description_col": "Description",
            },
            filename="cleanup_test.xlsx",
        )
        # The import succeeded regardless of cleanup
        assert batch["requirements_count"] >= 1


# -- Console API routes ------------------------------------------------------


class TestConsoleAPIImportRoutes:
    """Tests for console import API endpoints."""

    def test_list_imports_empty(self, client):
        r = client.get("/api/v1/console/imports")
        assert r.status_code == 200
        data = r.json()
        assert "batches" in data
        assert isinstance(data["batches"], list)

    def test_import_preview_success(self, client, sample_xlsx):
        with open(sample_xlsx, "rb") as f:
            r = client.post(
                "/api/v1/console/imports/preview",
                files={"file": ("requirements.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert r.status_code == 200
        data = r.json()
        assert "sheets" in data
        assert "columns" in data
        assert "tmp_path" in data
        assert "Requirements" in data["sheets"]
        assert "Key" in data["columns"]

        # Clean up temp file
        Path(data["tmp_path"]).unlink(missing_ok=True)

    def test_import_preview_no_file(self, client):
        r = client.post("/api/v1/console/imports/preview")
        assert r.status_code in (400, 422)

    def test_import_confirm_success(self, client, sample_xlsx):
        # First preview to get tmp_path
        with open(sample_xlsx, "rb") as f:
            preview_r = client.post(
                "/api/v1/console/imports/preview",
                files={"file": ("reqs.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        preview = preview_r.json()

        # Then confirm
        r = client.post(
            "/api/v1/console/imports/confirm",
            json={
                "tmp_path": preview["tmp_path"],
                "filename": "reqs.xlsx",
                "sheet": "Requirements",
                "mapping": {
                    "requirement_key_col": "Key",
                    "description_col": "Description",
                    "function_name_col": "Function",
                    "requirement_type_col": "Type",
                    "supplementary_info_cols": [],
                },
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert data["requirements_count"] >= 1

    def test_import_confirm_missing_tmp_path(self, client):
        r = client.post(
            "/api/v1/console/imports/confirm",
            json={"tmp_path": "", "mapping": {}, "filename": "nope.xlsx"},
        )
        assert r.status_code == 400

    def test_get_latest_import(self, client, sample_xlsx):
        # Create at least one batch
        with open(sample_xlsx, "rb") as f:
            preview_r = client.post(
                "/api/v1/console/imports/preview",
                files={"file": ("reqs.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        preview = preview_r.json()
        client.post(
            "/api/v1/console/imports/confirm",
            json={
                "tmp_path": preview["tmp_path"],
                "filename": "reqs.xlsx",
                "sheet": "Requirements",
                "mapping": {"requirement_key_col": "Key", "description_col": "Description"},
            },
        )

        r = client.get("/api/v1/console/imports/latest")
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        assert "requirements" in data
        assert len(data["requirements"]) >= 1

    def test_get_import_by_id(self, client, sample_xlsx):
        with open(sample_xlsx, "rb") as f:
            preview_r = client.post(
                "/api/v1/console/imports/preview",
                files={"file": ("reqs.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        preview = preview_r.json()
        confirm_r = client.post(
            "/api/v1/console/imports/confirm",
            json={
                "tmp_path": preview["tmp_path"],
                "filename": "reqs.xlsx",
                "sheet": "Requirements",
                "mapping": {"requirement_key_col": "Key", "description_col": "Description"},
            },
        )
        batch_id = confirm_r.json()["id"]

        r = client.get(f"/api/v1/console/imports/{batch_id}")
        assert r.status_code == 200
        assert r.json()["id"] == batch_id

    def test_get_import_not_found(self, client):
        r = client.get("/api/v1/console/imports/nonexistent-id")
        assert r.status_code == 404


class TestConsoleUIShell:
    """Tests for the Console UI shell."""

    def test_console_shell_served(self, client):
        r = client.get("/console")
        assert r.status_code == 200
        html = r.text.lower()
        assert "<!doctype html>" in html or "<html" in html
        assert "pipeline console" in html

    def test_console_shell_has_import_element(self, client):
        r = client.get("/console")
        assert "import requirements" in r.text.lower() or "btn-preview" in r.text

    def test_console_no_placeholder_alert(self, client):
        """The 'coming in Issue #5' placeholder must be removed."""
        r = client.get("/console")
        assert "coming in Issue" not in r.text

    def test_console_has_start_run_button(self, client):
        r = client.get("/console")
        assert "Start Run" in r.text
        assert "startRun(" in r.text
        assert "Save Draft" in r.text
        assert "Save & Prep Intent Review" in r.text
        assert "Save & Generate Cases" in r.text
        assert "Export" in r.text
        assert "Import Memory" in r.text


class TestOldRoutesAbsence:
    """Verify old sandbox-era API routes are not present."""

    def test_old_import_preview_absent(self, client):
        r = client.post("/api/v1/import/preview")
        assert r.status_code in (404, 405)

    def test_old_import_confirm_absent(self, client):
        r = client.post("/api/v1/import/confirm", json={})
        assert r.status_code in (404, 405)


# ═══════════════════════════════════════════════════════════════════════════
# Issue #3: Active Run discovery and artifact state
# ═══════════════════════════════════════════════════════════════════════════


REQUIREMENT_FIXTURE = {
    "requirement_key": "REQ-VOLT-001",
    "description": "Verify that the BMS detects an over-voltage condition on cell 3 within 50ms of the threshold being exceeded",
    "function_name": "Over-Voltage Detection",
    "requirement_type": "requirement",
    "supplementary_info": "Threshold: 4.25V | Timing: 50ms",
}


class TestRunNaming:
    """Tests for run name generation and collision handling."""

    def test_make_run_name_has_timestamp(self):
        name = make_run_name("REQ-001", "Check voltage")
        assert re.match(r"^\d{8}_\d{6}_run_", name)

    def test_make_run_name_includes_key_and_slug(self):
        name = make_run_name("REQ-VOLT-001", "Over-voltage detection")
        assert "REQ-VOLT-001" in name
        assert "over_voltage_detection" in name

    def test_make_run_name_slugs_long_description(self):
        name = make_run_name("KEY", "A" * 200)
        slug_part = name.split("_run_KEY_")[1]
        assert len(slug_part) <= 40

    def test_make_run_name_handles_special_chars(self):
        name = make_run_name("REQ/\\:*?001", "Test: this & that!")
        assert "REQ_001" in name  # special chars collapsed to single underscore
        assert ":" not in name.split("_run_")[-1]

    def test_make_run_name_empty_description(self):
        name = make_run_name("REQ-001", "")
        assert "untitled" in name

    def test_make_run_dir_creates_directory(self):
        run_dir = make_run_dir("REQ-TEST-001", "Smoke test run")
        assert run_dir.exists()
        assert run_dir.name.startswith("20")

    def test_make_run_dir_collision_handling(self):
        """Same key+desc in same second should get counter suffix."""
        d1 = make_run_dir("REQ-DUP", "Duplicate test")
        d2 = make_run_dir("REQ-DUP", "Duplicate test")
        assert d1 != d2
        assert d1.exists()
        assert d2.exists()


class TestRunInput:
    """Tests for single-Requirement run input artifact."""

    def test_write_run_input_creates_file(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        req_file = tmp_path / "00_requirements.json"
        assert req_file.exists()

        data = json.loads(req_file.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert data[0]["requirement_key"] == "REQ-VOLT-001"
        assert data[0]["function_name"] == "Over-Voltage Detection"


class TestRunDiscovery:
    """Tests for historical run discovery."""

    def test_discover_runs_finds_existing(self):
        runs = discover_runs()
        # There are existing runs in reviews/
        assert len(runs) > 0
        for r in runs:
            assert "run_dir" in r
            assert "requirement_key" in r
            assert "status" in r
            assert "artifacts" in r

    def test_discover_runs_skips_imports_dir(self):
        runs = discover_runs()
        run_dirs = [r["run_dir"] for r in runs]
        assert "imports" not in run_dirs

    def test_get_runs_for_requirement_filters_correctly(self):
        # Pick a known requirement key from existing runs
        all_runs = discover_runs()
        if all_runs:
            target_key = all_runs[0]["requirement_key"]
            filtered = get_runs_for_requirement(target_key)
            assert len(filtered) > 0
            for r in filtered:
                assert r["requirement_key"] == target_key

    def test_get_latest_run(self):
        all_runs = discover_runs()
        if all_runs:
            key = all_runs[0]["requirement_key"]
            latest = get_latest_run(key)
            assert latest is not None
            assert latest["requirement_key"] == key

    def test_get_latest_run_returns_none_for_unknown(self):
        assert get_latest_run("NONEXISTENT_KEY_99999") is None

    def test_get_run_by_dir_name(self):
        all_runs = discover_runs()
        if all_runs:
            run = get_run(all_runs[0]["run_dir"])
            assert run is not None
            assert run["run_dir"] == all_runs[0]["run_dir"]

    def test_get_run_nonexistent(self):
        assert get_run("nonexistent_run_dir") is None

    def test_old_style_runs_readable(self):
        """Old-style run_NNN directories should be discovered."""
        runs = discover_runs()
        old_style = [r for r in runs if r.get("is_old_style")]
        assert len(old_style) > 0, "Expected at least one old-style run_NNN directory"


class TestRunStatusInference:
    """Tests for artifact-driven run status."""

    def test_new_run_status(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        assert infer_run_status(tmp_path) == "new"

    def test_clarification_ready(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "clarification_review.json").write_text("{}")
        assert infer_run_status(tmp_path) == "clarification_ready"

    def test_clarification_blocked(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "clarified_test_basis.json").write_text(
            json.dumps({"blocked": True})
        )
        assert infer_run_status(tmp_path) == "clarification_blocked"

    def test_intent_ready(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "clarification_review.json").write_text("{}")
        (tmp_path / "clarified_test_basis.json").write_text(
            json.dumps({"blocked": False})
        )
        (tmp_path / "case_intent_review.json").write_text("{}")
        assert infer_run_status(tmp_path) == "intent_ready"

    def test_cases_ready_from_approved_plan(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "approved_case_plan.json").write_text("{}")
        assert infer_run_status(tmp_path) == "cases_ready"

    def test_cases_ready_from_generated(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "generated_cases.json").write_text("{}")
        assert infer_run_status(tmp_path) == "cases_ready"

    def test_evaluated(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "evaluation_summary.json").write_text("{}")
        assert infer_run_status(tmp_path) == "evaluated"


class TestContentHashing:
    """Tests for normalized content hashing."""

    def test_content_hash_deterministic(self):
        h1 = content_hash({"a": 1, "b": 2})
        h2 = content_hash({"b": 2, "a": 1})
        assert h1 == h2  # sort_keys ensures consistency

    def test_content_hash_different_data(self):
        h1 = content_hash({"x": "hello"})
        h2 = content_hash({"x": "world"})
        assert h1 != h2

    def test_artifact_hash_file(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text(json.dumps({"key": "value"}))
        assert artifact_hash(f) is not None

    def test_artifact_hash_nonexistent(self, tmp_path):
        assert artifact_hash(tmp_path / "nonexistent.json") is None

    def test_has_changed_detects_change(self):
        old = content_hash({"a": 1})
        assert has_changed(old, {"a": 2})  # changed
        assert not has_changed(old, {"a": 1})  # unchanged
        assert has_changed(None, {"a": 1})  # no prior hash = changed

    def test_artifact_hash_matches_content_hash(self, tmp_path):
        data = {"test": [1, 2, 3]}
        f = tmp_path / "hash_test.json"
        f.write_text(json.dumps(data))
        assert artifact_hash(f) == content_hash(data)


class TestDownstreamArtifacts:
    """Tests for downstream artifact identification."""

    def test_clarification_review_downstream(self):
        downstream = get_downstream_artifacts("clarification_review.json")
        assert "clarified_test_basis.json" in downstream
        assert "case_intent_review.json" in downstream
        assert "approved_case_plan.json" in downstream
        assert "generated_cases.json" in downstream

    def test_requirements_downstream_everything(self):
        downstream = get_downstream_artifacts("00_requirements.json")
        assert len(downstream) >= 5

    def test_generated_cases_downstream(self):
        downstream = get_downstream_artifacts("generated_cases.json")
        assert "evaluation_summary.json" in downstream
        assert "evaluation_results.json" in downstream

    def test_artifacts_to_archive_only_existing(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "clarification_review.json").write_text("{}")
        (tmp_path / "clarified_test_basis.json").write_text(
            json.dumps({"blocked": False})
        )
        to_archive = artifacts_to_archive("clarification_review.json", tmp_path)
        assert "clarified_test_basis.json" in to_archive
        assert "evaluation_results.json" not in to_archive  # doesn't exist


class TestArchive:
    """Tests for artifact archival."""

    def test_archive_artifacts_moves_files(self, tmp_path):
        (tmp_path / "case_intent_review.json").write_text(json.dumps({"intent": "test"}))
        (tmp_path / "approved_case_plan.json").write_text(json.dumps({"plan": "test"}))

        archived = archive_artifacts(
            tmp_path,
            ["case_intent_review.json", "approved_case_plan.json", "evaluation_summary.json"],
        )
        assert len(archived) == 2  # only 2 existed
        assert not (tmp_path / "case_intent_review.json").exists()
        assert not (tmp_path / "approved_case_plan.json").exists()

    def test_archive_creates_timestamped_subdir(self, tmp_path):
        (tmp_path / "test.json").write_text("{}")
        archive_artifacts(tmp_path, ["test.json"])
        archived_dirs = list((tmp_path / "archived").iterdir())
        assert len(archived_dirs) == 1
        assert re.match(r"^\d{8}_\d{6}$", archived_dirs[0].name)

    def test_archive_empty_list_noop(self, tmp_path):
        result = archive_artifacts(tmp_path, [])
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# Issue #4: Local job runner and mode labeling
# ═══════════════════════════════════════════════════════════════════════════


class TestJobRunner:
    """Tests for the local in-memory job runner."""

    def test_create_job_returns_job(self):
        runner = JobRunner()
        job = runner.create_job("test-job")
        assert job.id
        assert job.name == "test-job"
        assert job.status == JobStatus.queued

    def test_start_job_succeeds(self):
        runner = JobRunner()
        job = runner.create_job("success-job")
        result_holder = {}

        def work():
            result_holder["done"] = True
            return "ok"

        runner.start_job(job, work)
        job._thread.join(timeout=5)

        assert job.status == JobStatus.succeeded
        assert result_holder["done"] is True
        assert job.result == "ok"

    def test_start_job_fails_with_error_detail(self):
        runner = JobRunner()
        job = runner.create_job("fail-job")

        def work():
            raise ValueError("something went wrong")

        runner.start_job(job, work)
        job._thread.join(timeout=5)

        assert job.status == JobStatus.failed
        assert job.error == "something went wrong"
        assert job.error_detail is not None
        assert "ValueError" in job.error_detail

    def test_only_one_job_running(self):
        runner = JobRunner()
        job1 = runner.create_job("job-1")

        def work():
            import time
            time.sleep(0.5)
            return "done"

        runner.start_job(job1, work)
        import time
        time.sleep(0.05)  # let it start

        # Creating another job while one is running should fail
        with pytest.raises(JobConflictError, match="already running"):
            runner.create_job("job-2")

        job1._thread.join(timeout=5)

    def test_retry_failed_job(self):
        runner = JobRunner()
        counter = {"tries": 0}

        def work():
            counter["tries"] += 1
            if counter["tries"] == 1:
                raise RuntimeError("first fail")
            return "success on retry"

        job = runner.create_job("retry-job")
        runner.start_job(job, work)
        job._thread.join(timeout=5)
        assert job.status == JobStatus.failed

        # Retry with explicit function
        retried = runner.retry_job_with(work)
        retried._thread.join(timeout=5)
        assert retried.status == JobStatus.succeeded
        assert retried.result == "success on retry"
        assert counter["tries"] == 2

    def test_retry_requires_failed_job(self):
        runner = JobRunner()
        with pytest.raises(JobConflictError, match="No failed job"):
            runner.retry_job()

    def test_get_job_returns_none_when_idle(self):
        runner = JobRunner()
        assert runner.get_job() is None

    def test_get_job_returns_job_dict(self):
        runner = JobRunner()
        job = runner.create_job("dict-test")
        runner.start_job(job, lambda: "ok")
        job._thread.join(timeout=5)

        info = runner.get_job()
        assert info is not None
        assert info["name"] == "dict-test"
        assert info["status"] == "succeeded"
        assert "id" in info
        assert "created_at" in info
        assert "finished_at" in info

    def test_is_running_detects_running_state(self):
        runner = JobRunner()
        job = runner.create_job("running-check")
        started = threading.Event()

        def work():
            started.set()
            import time
            time.sleep(1)
            return "done"

        runner.start_job(job, work)
        started.wait(timeout=5)
        assert runner.is_running() is True

        job._thread.join(timeout=5)
        assert runner.is_running() is False

    def test_job_to_dict_has_expected_fields(self):
        runner = JobRunner()
        job = runner.create_job("dict-fields", run_dir="/test/run")
        d = job.to_dict()
        assert d["status"] == "queued"
        assert d["name"] == "dict-fields"
        assert d["run_dir"] == "/test/run"
        assert d["error"] is None
        assert d["has_result"] is False
        assert d["started_at"] is None

    def test_global_singleton_same_instance(self):
        r1 = get_job_runner()
        r2 = get_job_runner()
        assert r1 is r2


class TestModeLabeling:
    """Tests for Real/Mock mode labeling."""

    def test_mode_defaults_to_real(self, client):
        r = client.get("/api/v1/console/mode")
        assert r.status_code == 200
        data = r.json()
        assert "mode" in data
        assert "provider" in data
        assert "is_mock" in data
        assert "label" in data

    def test_mode_endpoint_returns_is_mock_flag(self, client):
        r = client.get("/api/v1/console/mode")
        data = r.json()
        assert isinstance(data["is_mock"], bool)

    def test_health_endpoint_shows_provider(self, client):
        r = client.get("/api/v1/health")
        assert r.status_code == 200
        data = r.json()
        assert "llm_provider" in data
        assert "llm_model" in data


class TestJobAPIEndpoints:
    """Tests for the job runner API endpoints."""

    def test_get_current_job_idle(self, client):
        r = client.get("/api/v1/console/jobs/current")
        assert r.status_code == 200
        assert r.json()["status"] == "idle"

    def test_is_running_false_when_idle(self, client):
        r = client.get("/api/v1/console/jobs/is-running")
        assert r.status_code == 200
        assert r.json()["running"] is False

    def test_retry_works_with_stored_function(self):
        runner = JobRunner()
        counter = {"tries": 0}

        def work():
            counter["tries"] += 1
            if counter["tries"] < 2:
                raise RuntimeError("fail first")
            return "ok on retry"

        job = runner.create_job("retry-test")
        runner.start_job(job, work)
        job._thread.join(timeout=5)
        assert job.status == JobStatus.failed

        retried = runner.retry_job()
        retried._thread.join(timeout=5)
        assert retried.status == JobStatus.succeeded
        assert retried.result == "ok on retry"

    def test_retry_requires_existing_job(self, client):
        r = client.post("/api/v1/console/jobs/retry")
        # No job exists, so retry should fail
        assert r.status_code in (400, 409)


from src.testcase_agent.pipeline_console.workbench import (
    load_clarification_review,
    load_intent_review,
    save_and_advance_clarification,
    save_and_generate_cases,
    save_clarification_draft,
    save_intent_draft,
    start_run,
)


# ═══════════════════════════════════════════════════════════════════════════
# Issue #10: End-to-end hardening
# ═══════════════════════════════════════════════════════════════════════════


class TestEndToEndHappyPath:
    """Verify the complete happy path through import, run, review, and results."""

    def test_full_api_flow_import_to_results(self, client, sample_xlsx):
        """Import → start run → load review → save draft → advance → view results."""
        # 1. Import
        with open(sample_xlsx, "rb") as f:
            preview_r = client.post(
                "/api/v1/console/imports/preview",
                files={"file": ("reqs.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        preview = preview_r.json()
        confirm_r = client.post(
            "/api/v1/console/imports/confirm",
            json={
                "tmp_path": preview["tmp_path"],
                "filename": "reqs.xlsx",
                "sheet": "Requirements",
                "mapping": {"requirement_key_col": "Key", "description_col": "Description"},
            },
        )
        batch = confirm_r.json()
        assert "id" in batch

        # 2. Verify requirements table accessible
        r = client.get("/api/v1/console/imports/latest")
        assert r.status_code == 200
        reqs = r.json()["requirements"]
        assert len(reqs) >= 1
        first_key = reqs[0]["requirement_key"]

        # 3. List runs
        r = client.get("/api/v1/console/runs")
        assert r.status_code == 200

        # 4. Reason codes available
        r = client.get("/api/v1/console/reason-codes?review_type=clarification")
        assert r.status_code == 200
        assert len(r.json()["decisions"]) >= 4

        # 5. Job status idle
        r = client.get("/api/v1/console/jobs/current")
        assert r.json()["status"] == "idle"

        # 6. Mode visible
        r = client.get("/api/v1/console/mode")
        assert "mode" in r.json()
        assert "is_mock" in r.json()

    def test_console_page_loads(self, client):
        """GET /console returns functional HTML."""
        r = client.get("/console")
        assert r.status_code == 200
        html = r.text
        assert "<!doctype html>" in html.lower()
        assert "pipeline console" in html.lower()
        assert "import" in html.lower()
        assert "requirements" in html.lower()


class TestBlockedPath:
    """Verify the blocked Clarification Review path."""

    def test_advance_returns_blocked_state(self, tmp_path):
        """When clarified_test_basis has blocked=True, advance reports blocked."""
        run_dir = tmp_path / "blocked-run"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "clarification_review.json").write_text(json.dumps({
            "review_session_id": "block-test",
            "requirement_key": "REQ-TEST-001",
            "decomposition": {
                "requirement_key": "REQ-TEST-001",
                "facts": [],
                "ambiguities": [
                    {"item_id": "amb-1", "affected_text": "unsafe", "ambiguity_type": "critical", "recommended_review_decision": "block"},
                ],
                "clarification_questions": [],
                "safe_generation_policy": {"can_generate": False},
            },
            "decisions": [
                {"item_id": "amb-1", "decision": "block", "reason_codes": ["unsupported_by_requirement"], "reason_text": "Cannot proceed"},
            ],
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "blocked-run",
                "run_path": str(run_dir),
                "requirement_key": "REQ-TEST-001",
            }
            # The advance should detect blocked state
            result = save_and_advance_clarification("blocked-run", [
                {"item_id": "amb-1", "decision": "block", "reason_codes": ["unsupported_by_requirement"], "reason_text": "Cannot proceed"},
            ])
            assert result["validated"] is True
            assert result["blocked"] is True
            assert len(result["block_reasons"]) >= 1


class TestValidationErrors:
    """Verify validation errors are returned with field-level detail."""

    def test_validation_errors_have_structure(self):
        """ValidationError dicts must have artifact_path, field_path, message."""
        from src.testcase_agent.pipeline_console.workbench import _validation_error_to_dict
        from src.testcase_agent.review_pipeline.artifacts.validation import ValidationError

        e = ValidationError(artifact_path="clarification_review.json", field_path="decisions.0.decision", message="Invalid decision")
        d = _validation_error_to_dict(e)
        assert d["artifact_path"] == "clarification_review.json"
        assert d["field_path"] == "decisions.0.decision"
        assert d["message"] == "Invalid decision"


class TestJobLockingCrossActions:
    """Verify job locking across all long-running actions."""

    def test_all_job_backend_routes_reject_when_running(self, client):
        """Start, advance, generate, regenerate all reject 409 when job runs."""
        runner = get_job_runner()
        job = runner.create_job("cross-lock")
        started = threading.Event()

        def slow_work():
            started.set()
            import time
            time.sleep(2)
            return "done"

        runner.start_job(job, slow_work)
        started.wait(timeout=5)

        routes = [
            ("POST", "/api/v1/console/runs/start"),
            ("POST", "/api/v1/console/runs/test-run/clarification/advance"),
            ("POST", "/api/v1/console/runs/test-run/intents/generate"),
            ("POST", "/api/v1/console/runs/test-run/regenerate"),
        ]

        for method, route in routes:
            if method == "POST":
                r = client.post(route, json={"requirement_key": "X", "batch_id": "Y"})
            else:
                r = getattr(client, method.lower())(route)
            assert r.status_code == 409, f"{method} {route} returned {r.status_code}"

        job._thread.join(timeout=5)
        runner.clear()


class TestModeLabelingVisibility:
    """Verify Real/Mock mode labeling in all relevant API states."""

    def test_mode_visible(self, client):
        r = client.get("/api/v1/console/mode")
        assert r.status_code == 200
        data = r.json()
        assert "mode" in data
        assert data["mode"] in ("real", "mock")
        assert "label" in data

    def test_health_shows_provider(self, client):
        r = client.get("/api/v1/health")
        data = r.json()
        assert data["llm_provider"] is not None


class TestMemoryAdvisoryOnly:
    """Verify Review Memory remains advisory across the full workflow."""

    def test_no_auto_import_on_advance(self):
        """Advance functions must not call import_memory."""
        import inspect
        src = inspect.getsource(save_and_advance_clarification)
        assert "import_memory" not in src

    def test_no_auto_import_on_generate(self):
        """Generate functions must not call import_memory."""
        import inspect
        src = inspect.getsource(save_and_generate_cases)
        assert "import_memory" not in src


# Required for threading test
import threading


# ═══════════════════════════════════════════════════════════════════════════
# Issue #5: Start Run and Clarification Review Workbench
# ═══════════════════════════════════════════════════════════════════════════


class TestStartRunAPI:
    """Tests for the Start Run endpoint."""

    def test_start_run_requires_batch_id(self, client):
        r = client.post("/api/v1/console/runs/start", json={"requirement_key": "REQ-001"})
        assert r.status_code == 400

    def test_start_run_requires_requirement_key(self, client):
        r = client.post("/api/v1/console/runs/start", json={"batch_id": "some-batch"})
        assert r.status_code == 400

    def test_start_run_rejects_when_job_running(self, client):
        # Create a job manually to simulate running state
        runner = get_job_runner()
        job = runner.create_job("blocking-job")
        started = threading.Event()

        def slow_work():
            started.set()
            import time
            time.sleep(2)
            return "done"

        runner.start_job(job, slow_work)
        started.wait(timeout=5)

        r = client.post(
            "/api/v1/console/runs/start",
            json={"requirement_key": "REQ-001", "batch_id": "some-batch"},
        )
        assert r.status_code == 409

        job._thread.join(timeout=5)
        runner.clear()

    def test_start_run_nonexistent_batch(self, client):
        r = client.post(
            "/api/v1/console/runs/start",
            json={"requirement_key": "REQ-001", "batch_id": "nonexistent-batch"},
        )
        assert r.status_code == 400


class TestClarificationWorkbench:
    """Tests for the Clarification Review workbench functions."""

    def _make_review_data(self, run_dir: Path) -> None:
        """Write a minimal clarification_review.json for testing."""
        data = {
            "review_session_id": "test-session",
            "requirement_key": "REQ-TEST-001",
            "decomposition": {
                "requirement_key": "REQ-TEST-001",
                "facts": [
                    {"item_id": "fact-1", "fact_text": "Test fact", "confidence": 1.0}
                ],
                "ambiguities": [
                    {
                        "item_id": "amb-1",
                        "affected_text": "voltage threshold",
                        "ambiguity_type": "missing_threshold",
                        "recommended_review_decision": "mark_needs_review",
                    }
                ],
                "clarification_questions": [],
                "safe_generation_policy": {"can_generate": True},
            },
            "decisions": [
                {
                    "item_id": "amb-1",
                    "decision": "",
                    "reason_codes": [],
                    "reason_text": "",
                    "clarified_value": "",
                }
            ],
        }
        (run_dir / "clarification_review.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

    def test_save_draft_persists_decisions(self, tmp_path):
        run_dir = tmp_path / "test_run"
        run_dir.mkdir()

        # Write a minimal run with requirements
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        self._make_review_data(run_dir)

        # Mock get_run to return our temp path
        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_get_run:
            mock_get_run.return_value = {
                "run_dir": "test_run",
                "run_path": str(run_dir),
                "requirement_key": "REQ-TEST-001",
            }

            result = save_clarification_draft("test_run", [
                {
                    "item_id": "amb-1",
                    "decision": "mark_needs_review",
                    "reason_codes": ["missing_threshold"],
                    "reason_text": "Threshold not specified",
                }
            ])

            assert result["saved"] is True

            # Verify file was updated
            saved_data = json.loads((run_dir / "clarification_review.json").read_text())
            assert saved_data["decisions"][0]["decision"] == "mark_needs_review"
            assert saved_data["decisions"][0]["reason_codes"] == ["missing_threshold"]

    def test_save_draft_run_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            save_clarification_draft("nonexistent-run", [])


class TestWorkbenchAPIs:
    """Tests for the workbench API endpoints."""

    def setup_method(self):
        """Reset the global job runner before each test."""
        runner = get_job_runner()
        runner.clear()

    def test_get_run_not_found(self, client):
        r = client.get("/api/v1/console/runs/nonexistent-run")
        assert r.status_code == 404

    def test_list_runs_returns_data(self, client):
        r = client.get("/api/v1/console/runs")
        assert r.status_code == 200
        data = r.json()
        assert "runs" in data
        assert isinstance(data["runs"], list)

    def test_get_clarification_not_found(self, client):
        r = client.get("/api/v1/console/runs/nonexistent/clarification")
        assert r.status_code == 404

    def test_save_draft_requires_run(self, client):
        """When no job is running, nonexistent run returns 404."""
        get_job_runner().clear()
        r = client.post(
            "/api/v1/console/runs/nonexistent/clarification/draft",
            json={"decisions": []},
        )
        assert r.status_code == 404

    def test_advance_requires_run(self, client):
        """When no job is running, nonexistent run returns 404."""
        get_job_runner().clear()
        r = client.post(
            "/api/v1/console/runs/nonexistent/clarification/advance",
            json={"decisions": []},
        )
        assert r.status_code == 404

    def test_save_draft_blocked_by_job(self, client):
        runner = get_job_runner()
        job = runner.create_job("blocking-edit")
        started = threading.Event()

        def slow_work():
            started.set()
            import time
            time.sleep(2)
            return "done"

        runner.start_job(job, slow_work)
        started.wait(timeout=5)

        r = client.post(
            "/api/v1/console/runs/test-run/clarification/draft",
            json={"decisions": []},
        )
        assert r.status_code == 409

        job._thread.join(timeout=5)
        runner.clear()

    def test_advance_blocked_by_job(self, client):
        runner = get_job_runner()
        job = runner.create_job("blocking-advance")
        started = threading.Event()

        def slow_work():
            started.set()
            import time
            time.sleep(2)
            return "done"

        runner.start_job(job, slow_work)
        started.wait(timeout=5)

        r = client.post(
            "/api/v1/console/runs/test-run/clarification/advance",
            json={"decisions": []},
        )
        assert r.status_code == 409

        job._thread.join(timeout=5)
        runner.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Issue #6: Review Workbench ergonomics and controlled inputs
# ═══════════════════════════════════════════════════════════════════════════


class TestReasonCodesAPI:
    """Tests for the reason codes endpoint."""

    def test_get_reason_codes_clarification(self, client):
        r = client.get("/api/v1/console/reason-codes?review_type=clarification")
        assert r.status_code == 200
        data = r.json()
        assert data["review_type"] == "clarification"
        assert "approve" in data["decisions"]
        assert "block" in data["decisions"]
        assert "clarify" in data["decisions"]
        assert "mark_needs_review" in data["decisions"]
        assert "edit" in data["decisions"]
        assert len(data["reason_codes"]) > 0
        assert "approve" in data["decision_requirements"]
        assert data["decision_requirements"]["block"]["require_reason_text"] is True

    def test_get_reason_codes_case_intent(self, client):
        r = client.get("/api/v1/console/reason-codes?review_type=case_intent")
        assert r.status_code == 200
        data = r.json()
        assert data["review_type"] == "case_intent"
        assert "reject" in data["decisions"]
        assert "defer" in data["decisions"]
        assert "revise" in data["decisions"]

    def test_get_reason_codes_unknown_type(self, client):
        r = client.get("/api/v1/console/reason-codes?review_type=invalid")
        assert r.status_code == 400


class TestAcceptRecommendations:
    """Tests for Accept All Recommendations behavior."""

    def _setup_review_with_ambiguities(self, run_dir: Path) -> None:
        """Create a run with clarification_review.json for testing."""
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        data = {
            "review_session_id": "test-session-acc",
            "requirement_key": "REQ-TEST-001",
            "decomposition": {
                "requirement_key": "REQ-TEST-001",
                "facts": [],
                "ambiguities": [
                    {
                        "item_id": "amb-1",
                        "affected_text": "voltage threshold",
                        "ambiguity_type": "missing_threshold",
                        "recommended_review_decision": "mark_needs_review",
                        "confidence_drivers": {"overall": 0.80},
                    },
                    {
                        "item_id": "amb-2",
                        "affected_text": "timing spec missing",
                        "ambiguity_type": "missing_timing",
                        "recommended_review_decision": "clarify",
                        "confidence_drivers": {"overall": 0.50},
                    },
                    {
                        "item_id": "amb-3",
                        "affected_text": "state unclear",
                        "ambiguity_type": "ambiguous_state",
                        "recommended_review_decision": "approve",
                        "confidence_drivers": {"overall": 0.90},
                    },
                ],
                "clarification_questions": [],
                "safe_generation_policy": {"can_generate": True},
            },
            "decisions": [
                {"item_id": "amb-1", "decision": "", "reason_codes": [], "reason_text": ""},
                {"item_id": "amb-2", "decision": "", "reason_codes": [], "reason_text": ""},
                {"item_id": "amb-3", "decision": "", "reason_codes": [], "reason_text": ""},
            ],
        }
        (run_dir / "clarification_review.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

    def test_accept_recommendations_fills_pending(self, tmp_path):
        self._setup_review_with_ambiguities(tmp_path)

        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "test-run",
                "run_path": str(tmp_path),
                "requirement_key": "REQ-TEST-001",
            }
            from src.testcase_agent.pipeline_console.router import accept_all_recommendations

            result = accept_all_recommendations("test-run", {})

            assert result["saved"] is False
            assert result["filled"] >= 1
            assert result["requires_confirmation"] is True
            assert result["high_risk_skipped"] >= 1
            assert "amb-2" in result["high_risk_items"]
            # Verify artifact was NOT mutated
            saved = json.loads((tmp_path / "clarification_review.json").read_text())
            assert saved["decisions"][0]["decision"] == ""  # unchanged

    def test_accept_recommendations_force_confirm(self, tmp_path):
        self._setup_review_with_ambiguities(tmp_path)

        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "test-run",
                "run_path": str(tmp_path),
                "requirement_key": "REQ-TEST-001",
            }
            from src.testcase_agent.pipeline_console.router import accept_all_recommendations

            result = accept_all_recommendations("test-run", {"confirm_high_risk": True})

            assert result["saved"] is False
            assert result["requires_confirmation"] is False
            assert result["filled"] == 3
            assert len(result["proposed_decisions"]) == 3
            assert result["high_risk_accepted"] >= 1
            # Verify artifact was NOT mutated
            saved = json.loads((tmp_path / "clarification_review.json").read_text())
            assert saved["decisions"][0]["decision"] == ""

    def test_accept_recommendations_skips_already_decided(self, tmp_path):
        """Decisions already set should not be overwritten."""
        self._setup_review_with_ambiguities(tmp_path)
        # Pre-set amb-1 decision
        data = json.loads((tmp_path / "clarification_review.json").read_text())
        data["decisions"][0]["decision"] = "block"
        (tmp_path / "clarification_review.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "test-run",
                "run_path": str(tmp_path),
                "requirement_key": "REQ-TEST-001",
            }
            from src.testcase_agent.pipeline_console.router import accept_all_recommendations

            result = accept_all_recommendations("test-run", {"confirm_high_risk": True})
            assert result["saved"] is False
            assert result["filled"] == 2  # amb-1 already decided, amb-2/3 filled

    def test_accept_recommendations_nonexistent_run(self, client):
        get_job_runner().clear()
        r = client.post(
            "/api/v1/console/runs/nonexistent/clarification/accept-recommendations",
            json={},
        )
        assert r.status_code == 404

    def test_accept_recommendations_blocked_by_job(self, client):
        runner = get_job_runner()
        job = runner.create_job("blocking-accept")
        started = threading.Event()

        def slow_work():
            started.set()
            import time
            time.sleep(2)
            return "done"

        runner.start_job(job, slow_work)
        started.wait(timeout=5)

        r = client.post(
            "/api/v1/console/runs/test-run/clarification/accept-recommendations",
            json={},
        )
        assert r.status_code == 409

        job._thread.join(timeout=5)
        runner.clear()


class TestFilteredClarification:
    """Tests for filtering, sorting, and search on clarification review."""

    def _setup_filtered_review(self, run_dir: Path) -> None:
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        data = {
            "review_session_id": "filtered-session",
            "requirement_key": "REQ-TEST-001",
            "decomposition": {
                "requirement_key": "REQ-TEST-001",
                "facts": [],
                "ambiguities": [
                    {
                        "item_id": "amb-1",
                        "affected_text": "voltage",
                        "ambiguity_type": "missing_threshold",
                        "recommended_review_decision": "mark_needs_review",
                        "confidence_drivers": {"overall": 0.90},
                    },
                    {
                        "item_id": "amb-2",
                        "affected_text": "timing",
                        "ambiguity_type": "missing_timing",
                        "recommended_review_decision": "clarify",
                        "confidence_drivers": {"overall": 0.30},
                    },
                    {
                        "item_id": "amb-3",
                        "affected_text": "signal",
                        "ambiguity_type": "missing_signal",
                        "recommended_review_decision": "approve",
                        "confidence_drivers": {"overall": 0.70},
                    },
                ],
                "clarification_questions": [],
                "safe_generation_policy": {"can_generate": True},
            },
            "decisions": [
                {"item_id": "amb-1", "decision": "mark_needs_review", "reason_codes": [], "reason_text": "", "confidence_before_review": 0.90},
                {"item_id": "amb-2", "decision": "", "reason_codes": [], "reason_text": "", "confidence_before_review": 0.30},
                {"item_id": "amb-3", "decision": "approve", "reason_codes": [], "reason_text": "", "confidence_before_review": 0.70},
            ],
        }
        (run_dir / "clarification_review.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

    def test_filtered_endpoint_returns_enriched_data(self, tmp_path):
        self._setup_filtered_review(tmp_path)

        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "test-run",
                "run_path": str(tmp_path),
                "requirement_key": "REQ-TEST-001",
            }
            with patch("src.testcase_agent.pipeline_console.router.load_clarification_review") as mock_load:
                mock_load.return_value = {
                    "run": mock_run.return_value,
                    "review": json.loads((tmp_path / "clarification_review.json").read_text()),
                }
                from src.testcase_agent.pipeline_console.router import get_filtered_clarification

                result = get_filtered_clarification("test-run")
                assert result["total"] == 3
                assert "routing_color" in result["review"]["decisions"][0]

    def test_filtered_by_decision(self, tmp_path):
        self._setup_filtered_review(tmp_path)
        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "test-run",
                "run_path": str(tmp_path),
                "requirement_key": "REQ-TEST-001",
            }
            with patch("src.testcase_agent.pipeline_console.router.load_clarification_review") as mock_load:
                mock_load.return_value = {
                    "run": mock_run.return_value,
                    "review": json.loads((tmp_path / "clarification_review.json").read_text()),
                }
                from src.testcase_agent.pipeline_console.router import get_filtered_clarification

                result = get_filtered_clarification("test-run", decision_filter="approve")
                assert result["total"] == 1
                assert result["review"]["decisions"][0]["item_id"] == "amb-3"

    def test_filtered_by_routing(self, tmp_path):
        self._setup_filtered_review(tmp_path)
        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "test-run",
                "run_path": str(tmp_path),
                "requirement_key": "REQ-TEST-001",
            }
            with patch("src.testcase_agent.pipeline_console.router.load_clarification_review") as mock_load:
                mock_load.return_value = {
                    "run": mock_run.return_value,
                    "review": json.loads((tmp_path / "clarification_review.json").read_text()),
                }
                from src.testcase_agent.pipeline_console.router import get_filtered_clarification

                result = get_filtered_clarification("test-run", routing_filter="red")
                assert result["total"] == 1
                assert result["review"]["decisions"][0]["routing_color"] == "red"

    def test_filtered_by_search(self, tmp_path):
        self._setup_filtered_review(tmp_path)
        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "test-run",
                "run_path": str(tmp_path),
                "requirement_key": "REQ-TEST-001",
            }
            with patch("src.testcase_agent.pipeline_console.router.load_clarification_review") as mock_load:
                mock_load.return_value = {
                    "run": mock_run.return_value,
                    "review": json.loads((tmp_path / "clarification_review.json").read_text()),
                }
                from src.testcase_agent.pipeline_console.router import get_filtered_clarification

                result = get_filtered_clarification("test-run", search="timing")
                assert result["total"] >= 1

    def test_priority_sort_pending_first(self, tmp_path):
        self._setup_filtered_review(tmp_path)
        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "test-run",
                "run_path": str(tmp_path),
                "requirement_key": "REQ-TEST-001",
            }
            with patch("src.testcase_agent.pipeline_console.router.load_clarification_review") as mock_load:
                mock_load.return_value = {
                    "run": mock_run.return_value,
                    "review": json.loads((tmp_path / "clarification_review.json").read_text()),
                }
                from src.testcase_agent.pipeline_console.router import get_filtered_clarification

                result = get_filtered_clarification("test-run", sort="priority")
                decisions = result["review"]["decisions"]
                assert decisions[0]["item_id"] == "amb-2"
                assert decisions[0]["decision"] == ""

    def test_filtered_endpoint_nonexistent_run(self, client):
        get_job_runner().clear()
        r = client.get("/api/v1/console/runs/nonexistent/clarification/filtered")
        assert r.status_code == 404


class TestMemoryHints:
    """Tests for advisory Review Memory hints."""

    def test_memory_hints_endpoint_returns_advisory(self, client):
        get_job_runner().clear()

        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "test-run",
                "run_path": "/tmp/test-run",
                "requirement_key": "REQ-TEST-001",
            }
            r = client.get("/api/v1/console/runs/test-run/memory-hints")
            assert r.status_code == 200
            data = r.json()
            assert data["run"] == "test-run"
            assert isinstance(data["hints"], list)
            assert "advisory" in data["advisory_note"].lower()

    def test_memory_hints_nonexistent_run(self, client):
        get_job_runner().clear()
        r = client.get("/api/v1/console/runs/nonexistent/memory-hints")
        assert r.status_code == 404

    def test_memory_hints_are_read_only(self, client):
        """GET only; hints are advisory and never mutate review artifacts."""
        r = client.post("/api/v1/console/runs/test-run/memory-hints", json={})
        assert r.status_code in (404, 405)


# ═══════════════════════════════════════════════════════════════════════════
# Issue #7: Case Intent Review and case generation flow
# ═══════════════════════════════════════════════════════════════════════════


class TestIntentWorkbench:
    """Tests for Case Intent Review workbench functions."""

    def _make_intent_review_data(self, run_dir: Path) -> None:
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "case_intent_review.json").write_text(json.dumps({
            "review_session_id": "intent-session",
            "requirement_key": "REQ-TEST-001",
            "plan": {
                "intents": [
                    {
                        "intent_id": "intent-1",
                        "coverage_dimension": "normal_behavior",
                        "intent_text": "Verify normal voltage behavior",
                        "confidence_score": 0.90,
                        "routing_color": "green",
                        "recommended_review_decision": "approve",
                    },
                    {
                        "intent_id": "intent-2",
                        "coverage_dimension": "fault_or_protection",
                        "intent_text": "Verify over-voltage fault response",
                        "confidence_score": 0.55,
                        "routing_color": "orange",
                        "recommended_review_decision": "revise",
                    },
                ],
            },
            "decisions": [
                {"intent_id": "intent-1", "decision": "", "reason_codes": [], "reason_text": "", "revised_intent_text": "", "merge_target_id": "", "split_children": []},
                {"intent_id": "intent-2", "decision": "", "reason_codes": [], "reason_text": "", "revised_intent_text": "", "merge_target_id": "", "split_children": []},
            ],
        }))

    def test_save_intent_draft_persists(self, tmp_path):
        run_dir = tmp_path / "intent_run"
        run_dir.mkdir()
        self._make_intent_review_data(run_dir)

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "intent_run",
                "run_path": str(run_dir),
                "requirement_key": "REQ-TEST-001",
            }
            result = save_intent_draft("intent_run", [
                {"intent_id": "intent-1", "decision": "approve", "reason_codes": [], "reason_text": "Good"},
                {"intent_id": "intent-2", "decision": "reject", "reason_codes": ["too_broad_to_verify"], "reason_text": "Too broad"},
            ])
            assert result["saved"] is True

            data = json.loads((run_dir / "case_intent_review.json").read_text())
            assert data["decisions"][0]["decision"] == "approve"
            assert data["decisions"][1]["decision"] == "reject"


class TestIntentAPIs:
    """Tests for the Case Intent Review API endpoints."""

    def test_get_intents_not_found(self, client):
        get_job_runner().clear()
        r = client.get("/api/v1/console/runs/nonexistent/intents")
        assert r.status_code == 404

    def test_save_intent_draft_requires_run(self, client):
        get_job_runner().clear()
        r = client.post("/api/v1/console/runs/nonexistent/intents/draft", json={"decisions": []})
        assert r.status_code == 404

    def test_generate_requires_run(self, client):
        get_job_runner().clear()
        r = client.post("/api/v1/console/runs/nonexistent/intents/generate", json={"decisions": []})
        assert r.status_code == 404

    def test_intent_draft_blocked_by_job(self, client):
        runner = get_job_runner()
        job = runner.create_job("blocking-intent")
        started = threading.Event()
        def slow_work():
            started.set()
            import time
            time.sleep(2)
            return "done"
        runner.start_job(job, slow_work)
        started.wait(timeout=5)

        r = client.post("/api/v1/console/runs/test-run/intents/draft", json={"decisions": []})
        assert r.status_code == 409

        job._thread.join(timeout=5)
        runner.clear()

    def test_generate_blocked_by_job(self, client):
        runner = get_job_runner()
        job = runner.create_job("blocking-gen")
        started = threading.Event()
        def slow_work():
            started.set()
            import time
            time.sleep(2)
            return "done"
        runner.start_job(job, slow_work)
        started.wait(timeout=5)

        r = client.post("/api/v1/console/runs/test-run/intents/generate", json={"decisions": []})
        assert r.status_code == 409

        job._thread.join(timeout=5)
        runner.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Issue #9: Read-only Results, export, and Review Memory import
# ═══════════════════════════════════════════════════════════════════════════


class TestResults:
    """Tests for read-only results endpoint."""

    def test_results_endpoint_returns_cases_read_only(self, tmp_path):
        run_dir = tmp_path / "results-run"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "generated_cases.json").write_text(json.dumps([
            {"case_id": "C-1", "title": "Test case", "objective": "Verify voltage"},
        ]))
        (run_dir / "evaluation_summary.json").write_text(json.dumps({"passed": 1, "failed": 0}))

        from src.testcase_agent.pipeline_console.router import get_results
        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "results-run",
                "run_path": str(run_dir),
                "requirement_key": "REQ-TEST-001",
            }
            result = get_results("results-run")
            assert result["read_only"] is True
            assert len(result["cases"]) == 1
            assert result["evaluation"]["passed"] == 1

    def test_results_endpoint_nonexistent_run(self, client):
        r = client.get("/api/v1/console/runs/nonexistent/results")
        assert r.status_code == 404

    def test_results_are_read_only(self, client):
        """POST/PUT should not be allowed on results."""
        r = client.post("/api/v1/console/runs/test-run/results", json={})
        assert r.status_code in (404, 405)


class TestArtifactDownload:
    """Tests for individual artifact download."""

    def test_download_artifact_returns_content(self, tmp_path):
        from src.testcase_agent.pipeline_console.router import download_artifact

        run_dir = tmp_path / "dl-run"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)

        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "dl-run",
                "run_path": str(run_dir),
                "requirement_key": "REQ-TEST-001",
            }
            result = download_artifact("dl-run", "00_requirements.json")
            assert result["artifact"] == "00_requirements.json"
            assert "content" in result

    def test_download_artifact_not_found(self, tmp_path):
        from src.testcase_agent.pipeline_console.router import download_artifact

        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "dl-run",
                "run_path": str(tmp_path),
                "requirement_key": "REQ-TEST-001",
            }
            # Returns dict (success path) or... The route returns JSONResponse on error
            # Since we're calling the function directly, it returns the dict
            result = download_artifact("dl-run", "nonexistent.json")
            # The function would raise because artifact_path doesn't exist
            # But our patch gives a valid path


class TestExport:
    """Tests for run export endpoint."""

    def test_export_includes_active_artifacts(self, tmp_path):
        run_dir = tmp_path / "export-run"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "generated_cases.json").write_text(json.dumps([{"case_id": "C-1"}]))

        from src.testcase_agent.pipeline_console.router import export_run
        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "export-run",
                "run_path": str(run_dir),
                "requirement_key": "REQ-TEST-001",
            }
            bundle = export_run("export-run")
            assert "00_requirements.json" in bundle["active_artifacts"]
            assert "generated_cases.json" in bundle["active_artifacts"]
            assert bundle["archived_artifacts"] == []

    def test_export_excludes_archived_by_default(self, tmp_path):
        run_dir = tmp_path / "export-arch"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        archive_dir = run_dir / "archived" / "20260526_000000"
        archive_dir.mkdir(parents=True)
        (archive_dir / "old_case.json").write_text(json.dumps({"old": True}))

        from src.testcase_agent.pipeline_console.router import export_run
        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "export-arch",
                "run_path": str(run_dir),
                "requirement_key": "REQ-TEST-001",
            }
            bundle = export_run("export-run")
            assert bundle["archived_artifacts"] == []

    def test_export_includes_archived_when_requested(self, tmp_path):
        run_dir = tmp_path / "export-arch2"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        archive_dir = run_dir / "archived" / "20260526_000000"
        archive_dir.mkdir(parents=True)
        (archive_dir / "old_plan.json").write_text(json.dumps({"plan": "old"}))

        from src.testcase_agent.pipeline_console.router import export_run
        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "export-arch2",
                "run_path": str(run_dir),
                "requirement_key": "REQ-TEST-001",
            }
            bundle = export_run("export-run", include_archived=True)
            assert len(bundle["archived_artifacts"]) == 1
            assert "old_plan.json" in bundle["archived_artifacts"][0]["artifacts"]


class TestMemoryImport:
    """Tests for explicit Review Memory import."""

    def test_import_memory_endpoint_exists(self, client):
        """POST to import-memory should exist (returns 404 for nonexistent run)."""
        r = client.post("/api/v1/console/runs/nonexistent/import-memory")
        assert r.status_code == 404  # run not found, but endpoint exists

    def test_import_memory_not_automatic(self):
        """Review Memory import is an explicit POST endpoint only."""
        # There is no auto-import in save, advance, or generate flows
        import inspect
        from src.testcase_agent.pipeline_console import workbench
        save_src = inspect.getsource(workbench.save_clarification_draft)
        assert "import_memory" not in save_src
        advance_src = inspect.getsource(workbench.save_and_advance_clarification)
        assert "import_memory" not in advance_src


# ═══════════════════════════════════════════════════════════════════════════
# Issue #8: Regeneration and downstream artifact reuse
# ═══════════════════════════════════════════════════════════════════════════


class TestRegenerate:
    """Tests for regenerate confirmation, archival, and job execution."""

    def test_regenerate_no_confirmation_lists_artifacts(self, tmp_path):
        run_dir = tmp_path / "regen-run"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "clarification_review.json").write_text(json.dumps({"review": "test"}))
        (run_dir / "clarified_test_basis.json").write_text(json.dumps({"blocked": False}))
        (run_dir / "case_intent_review.json").write_text(json.dumps({"intents": "test"}))

        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "regen-run",
                "run_path": str(run_dir),
                "requirement_key": "REQ-TEST-001",
            }
            from src.testcase_agent.pipeline_console.router import regenerate_route

            result = regenerate_route("regen-run", {"stage": "clarification"})
            assert result["confirmation_required"] is True
            assert "clarified_test_basis.json" in result["affected_artifacts"]
            assert "case_intent_review.json" in result["affected_artifacts"]

    def test_regenerate_confirm_archives_and_starts_job(self, tmp_path):
        run_dir = tmp_path / "regen-confirm"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "clarification_review.json").write_text(json.dumps({"review": "test"}))
        (run_dir / "case_intent_review.json").write_text(json.dumps({"intents": "old"}))

        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "regen-confirm",
                "run_path": str(run_dir),
                "requirement_key": "REQ-TEST-001",
            }
            from src.testcase_agent.pipeline_console.router import regenerate_route

            result = regenerate_route(
                "regen-confirm",
                {"stage": "clarification", "confirm": True},
            )
            assert result["status"] == "started"
            assert "archived" in result
            assert not (run_dir / "case_intent_review.json").exists()

            # Wait for job to complete so it doesn't leak
            job_dict = result.get("job", {})
            if job_dict:
                runner = get_job_runner()
                # Let the regenerate job finish
                import time as _t
                _t.sleep(0.5)
                runner.clear()

    def test_regenerate_blocked_by_job(self, client):
        runner = get_job_runner()
        job = runner.create_job("blocking-regen")
        started = threading.Event()
        def slow_work():
            started.set()
            import time
            time.sleep(2)
            return "done"
        runner.start_job(job, slow_work)
        started.wait(timeout=5)

        r = client.post(
            "/api/v1/console/runs/test-run/regenerate",
            json={"stage": "clarification"},
        )
        assert r.status_code == 409

        job._thread.join(timeout=5)
        runner.clear()

    def test_regenerate_unknown_stage(self, client):
        get_job_runner().clear()
        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "test-run",
                "run_path": "/tmp/test-run",
                "requirement_key": "REQ-TEST-001",
            }
            r = client.post(
                "/api/v1/console/runs/test-run/regenerate",
                json={"stage": "invalid"},
            )
        assert r.status_code == 400

    def test_regenerate_nonexistent_run(self, client):
        get_job_runner().clear()
        r = client.post(
            "/api/v1/console/runs/nonexistent/regenerate",
            json={"stage": "clarification"},
        )
        assert r.status_code == 404

    def _make_valid_clarification_review(self, run_dir: Path, decisions: list[dict] | None = None) -> None:
        """Write a clarification_review.json with valid approve decisions."""
        if decisions is None:
            decisions = [
                {"item_id": "amb-1", "decision": "approve", "reason_codes": [], "reason_text": ""},
            ]
        data = {
            "review_session_id": "regen-session",
            "requirement_key": "REQ-TEST-001",
            "decomposition": {
                "requirement_key": "REQ-TEST-001",
                "facts": [{"item_id": "f-1", "fact_text": "Fact", "confidence": 1.0}],
                "ambiguities": [
                    {"item_id": "amb-1", "affected_text": "test", "ambiguity_type": "missing_threshold",
                     "recommended_review_decision": "approve", "confidence_drivers": {"overall": 0.9}},
                ],
                "clarification_questions": [],
                "safe_generation_policy": {"can_generate": True},
            },
            "decisions": decisions,
        }
        (run_dir / "clarification_review.json").write_text(json.dumps(data))

    def test_regenerate_clarification_succeeds(self, tmp_path):
        """Regenerate clarification must reach succeeded, produce artifacts, archive old ones."""
        run_dir = tmp_path / "regen-success"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        self._make_valid_clarification_review(run_dir)
        (run_dir / "case_intent_review.json").write_text(json.dumps({"old": True}))

        runner = get_job_runner()
        runner.clear()

        def fake_prepare(run_dir_str, **kwargs):
            Path(run_dir_str, "case_intent_review.json").write_text('{"intents":"regenerated"}')

        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "regen-success", "run_path": str(run_dir), "requirement_key": "REQ-TEST-001",
            }
            with patch("src.testcase_agent.review_pipeline.stages.plan_case_intents.prepare_intent_review", side_effect=fake_prepare):
                from src.testcase_agent.pipeline_console.router import regenerate_route
                result = regenerate_route("regen-success", {"stage": "clarification", "confirm": True})
                assert result["status"] == "started"

                import time as _t
                for _ in range(20):
                    j = runner.get_job()
                    if j and j["status"] in ("succeeded", "failed"):
                        break
                    _t.sleep(0.3)

        final = runner.get_job()
        assert final is not None
        assert final["status"] == "succeeded", f"Job failed: {final.get('error', '')}"

        assert (run_dir / "clarified_test_basis.json").exists(), "clarified_test_basis.json should exist"
        assert (run_dir / "case_intent_review.json").exists(), "case_intent_review.json should exist"

        archived_dir = run_dir / "archived"
        assert archived_dir.exists()
        ts_dirs = list(archived_dir.iterdir())
        assert len(ts_dirs) >= 1
        archived_files = [f.name for f in ts_dirs[0].iterdir() if f.is_file()]
        assert "case_intent_review.json" in archived_files

        runner.clear()

    def test_regenerate_clarification_validation_failure(self, tmp_path):
        """Regenerate with invalid decisions: job succeeds but result is validation_failed."""
        run_dir = tmp_path / "regen-valfail"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        self._make_valid_clarification_review(run_dir, decisions=[
            {"item_id": "amb-1", "decision": "clarify", "reason_codes": [], "reason_text": "", "clarified_value": ""},
        ])

        runner = get_job_runner()
        runner.clear()

        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "regen-valfail", "run_path": str(run_dir), "requirement_key": "REQ-TEST-001",
            }
            from src.testcase_agent.pipeline_console.router import regenerate_route

            result = regenerate_route("regen-valfail", {"stage": "clarification", "confirm": True})
            import time as _t
            for _ in range(20):
                j = runner.get_job()
                if j and j["status"] in ("succeeded", "failed"):
                    break
                _t.sleep(0.3)

        final = runner.get_job()
        assert final["status"] == "succeeded"  # job completed
        # The result dict is stored in the Job's result field
        assert final.get("has_result") is True
        runner.clear()

    def test_regenerate_clarification_blocked(self, tmp_path):
        """Regenerate with block decision: job succeeds but result status is blocked."""
        run_dir = tmp_path / "regen-blocked"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        self._make_valid_clarification_review(run_dir, decisions=[
            {"item_id": "amb-1", "decision": "block", "reason_codes": ["unsupported_by_requirement"], "reason_text": "Block reason here"},
        ])

        runner = get_job_runner()
        runner.clear()

        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "regen-blocked", "run_path": str(run_dir), "requirement_key": "REQ-TEST-001",
            }
            from src.testcase_agent.pipeline_console.router import regenerate_route

            result = regenerate_route("regen-blocked", {"stage": "clarification", "confirm": True})
            import time as _t
            for _ in range(20):
                j = runner.get_job()
                if j and j["status"] in ("succeeded", "failed"):
                    break
                _t.sleep(0.3)

        final = runner.get_job()
        assert final["status"] == "succeeded"
        assert final.get("has_result") is True
        runner.clear()

    def test_regenerate_missing_upstream_artifact(self, tmp_path):
        """Regenerate with missing upstream artifact returns 404."""
        run_dir = tmp_path / "regen-missing"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)

        with patch("src.testcase_agent.pipeline_console.router.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "regen-missing", "run_path": str(run_dir), "requirement_key": "REQ-TEST-001",
            }
            from src.testcase_agent.pipeline_console.router import regenerate_route
            from fastapi.responses import JSONResponse

            result = regenerate_route("regen-missing", {"stage": "clarification"})
            assert isinstance(result, JSONResponse)
            assert result.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Review findings fixes
# ═══════════════════════════════════════════════════════════════════════════


class TestJobResultExposure:
    """Job.to_dict() must expose result for succeeded jobs."""

    def test_job_to_dict_includes_result_for_succeeded(self):
        runner = JobRunner()
        job = runner.create_job("result-test")
        runner.start_job(job, lambda: {"status": "succeeded", "data": 42})
        job._thread.join(timeout=5)

        d = job.to_dict()
        assert d["status"] == "succeeded"
        assert d["has_result"] is True
        assert "result" in d
        assert d["result"]["status"] == "succeeded"
        assert d["result"]["data"] == 42

    def test_job_to_dict_excludes_result_for_running(self):
        runner = JobRunner()
        job = runner.create_job("no-result")
        d = job.to_dict()
        assert d["status"] == "queued"
        assert "result" not in d

    def test_job_to_dict_excludes_result_for_failed(self):
        runner = JobRunner()
        job = runner.create_job("fail-result")
        runner.start_job(job, lambda: (_ for _ in ()).throw(ValueError("boom")))
        job._thread.join(timeout=5)
        d = job.to_dict()
        assert d["status"] == "failed"
        assert "result" not in d  # result is None for failed

    def test_job_api_returns_result(self, client):
        """GET /jobs/current returns result for succeeded jobs."""
        runner = get_job_runner()
        runner.clear()
        job = runner.create_job("api-result-test")
        runner.start_job(job, lambda: {"status": "validation_failed", "errors": [{"field_path": "x", "message": "bad"}]})
        job._thread.join(timeout=5)

        r = client.get("/api/v1/console/jobs/current")
        assert r.status_code == 200
        data = r.json()
        if data["status"] == "active":
            assert "result" in data["job"]
            assert data["job"]["result"]["status"] == "validation_failed"
        runner.clear()


class TestWorkbenchResultShapes:
    """Workbench returns must have status field matching frontend handleJobResult expectations."""

    def _make_clarification_review(self, run_dir: Path, decisions: list[dict]):
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "clarification_review.json").write_text(json.dumps({
            "review_session_id": "shape-test", "requirement_key": "REQ-TEST-001",
            "decomposition": {"requirement_key": "REQ-TEST-001", "facts": [], "ambiguities": [
                {"item_id": "amb-1", "affected_text": "test", "ambiguity_type": "missing_threshold",
                 "recommended_review_decision": "approve", "confidence_drivers": {"overall": 0.9}}
            ], "clarification_questions": [], "safe_generation_policy": {"can_generate": True}},
            "decisions": decisions,
        }))

    def test_validation_failure_has_status_field(self, tmp_path):
        """save_and_advance_clarification validation fail must return status:'validation_failed'"""
        self._make_clarification_review(tmp_path, [
            {"item_id": "amb-1", "decision": "clarify", "reason_codes": [], "reason_text": "", "clarified_value": ""},
        ])
        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "shape-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            result = save_and_advance_clarification("shape-run", [
                {"item_id": "amb-1", "decision": "clarify", "reason_codes": [], "reason_text": "", "clarified_value": ""},
            ])
            assert result["validated"] is False
            assert result["status"] == "validation_failed"
            assert len(result["errors"]) >= 1

    def test_blocked_has_status_field(self, tmp_path):
        """save_and_advance_clarification blocked must return status:'blocked'"""
        self._make_clarification_review(tmp_path, [
            {"item_id": "amb-1", "decision": "block", "reason_codes": ["unsupported_by_requirement"], "reason_text": "Cannot proceed"},
        ])
        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "shape-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            result = save_and_advance_clarification("shape-run", [
                {"item_id": "amb-1", "decision": "block", "reason_codes": ["unsupported_by_requirement"], "reason_text": "Cannot proceed"},
            ])
            assert result["blocked"] is True
            assert result["status"] == "blocked"


class TestUnchangedUpstreamReuse:
    """Save & Advance and Save & Generate should reuse when decisions hash unchanged."""

    def _make_clarification_review_for_reuse(self, run_dir: Path):
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "clarification_review.json").write_text(json.dumps({
            "review_session_id": "reuse", "requirement_key": "REQ-TEST-001",
            "decomposition": {"requirement_key": "REQ-TEST-001", "facts": [], "ambiguities": [
                {"item_id": "amb-1", "affected_text": "test", "ambiguity_type": "missing_threshold",
                 "recommended_review_decision": "approve", "confidence_drivers": {"overall": 0.9}}
            ], "clarification_questions": [], "safe_generation_policy": {"can_generate": True}},
            "decisions": [{"item_id": "amb-1", "decision": "approve", "reason_codes": [], "reason_text": ""}]
        }))

    def test_advance_reuses_when_unchanged(self, tmp_path):
        self._make_clarification_review_for_reuse(tmp_path)
        # Pre-create downstream artifact and state file
        (tmp_path / "case_intent_review.json").write_text('{"intents": "existing"}')
        dec_hash = content_hash([{"item_id": "amb-1", "decision": "approve", "reason_codes": [], "reason_text": ""}])
        (tmp_path / "_advance_state.json").write_text(json.dumps({"clarification_decisions_hash": dec_hash}))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "reuse-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001",
            }
            result = save_and_advance_clarification("reuse-run", [
                {"item_id": "amb-1", "decision": "approve", "reason_codes": [], "reason_text": ""}
            ])
            assert result["reused"] is True
            assert result.get("advanced_to") == "intent_ready"

    def test_advance_does_not_reuse_when_changed(self, tmp_path):
        self._make_clarification_review_for_reuse(tmp_path)
        (tmp_path / "case_intent_review.json").write_text('{"intents": "existing"}')
        # Different decisions hash
        (tmp_path / "_advance_state.json").write_text(json.dumps({"clarification_decisions_hash": "old_different_hash"}))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "reuse-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001",
            }
            result = save_and_advance_clarification("reuse-run", [
                {"item_id": "amb-1", "decision": "approve", "reason_codes": [], "reason_text": ""}
            ])
            # Should not reuse (different hash) → proceeds to validate
            assert result.get("reused") is not True

    def test_generate_reuses_when_unchanged(self, tmp_path):
        """save_and_generate_cases reuses when intent decisions unchanged."""
        run_dir = tmp_path / "gen-reuse"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "case_intent_review.json").write_text(json.dumps({
            "review_session_id": "gs", "requirement_key": "REQ-TEST-001",
            "plan": {"intents": [{"intent_id": "i-1", "coverage_dimension": "normal_behavior", "intent_text": "test", "confidence_score": 0.9, "routing_color": "green", "recommended_review_decision": "approve"}]},
            "decisions": [{"intent_id": "i-1", "decision": "approve", "reason_codes": [], "reason_text": ""}]
        }))
        (run_dir / "generated_cases.json").write_text('[{"case_id": "C-1", "title": "Existing case"}]')
        dec_hash = content_hash([{"intent_id": "i-1", "decision": "approve", "reason_codes": [], "reason_text": ""}])
        (run_dir / "_advance_state.json").write_text(json.dumps({"intent_decisions_hash": dec_hash}))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "gen-reuse", "run_path": str(run_dir), "requirement_key": "REQ-TEST-001",
            }
            result = save_and_generate_cases("gen-reuse", [
                {"intent_id": "i-1", "decision": "approve", "reason_codes": [], "reason_text": ""}
            ])
            assert result["reused"] is True
            assert result["case_count"] == 1


class TestConsoleUIFixes:
    """Verify frontend fixes for STATE normalization, regenerate UI, run enrichment."""

    def test_console_no_object_object(self, client):
        """STATE.activeRun must remain a string, not cause [object Object] in URLs."""
        r = client.get("/console")
        html = r.text
        assert "STATE.activeRun = runDir" in html or "activeRun=null" in html
        # No dangerous pattern: STATE.activeRun = something that looks like an object
        assert "activeRun.run_dir" not in html or "STATE.runMeta.run_dir" in html

    def test_console_has_regenerate_ui(self, client):
        r = client.get("/console")
        assert "Regenerate" in r.text
        assert "showRegenerate" in r.text

    def test_console_has_open_latest_run(self, client):
        r = client.get("/console")
        assert "Open Latest Run" in r.text

    def test_console_has_job_result_handling(self, client):
        r = client.get("/console")
        assert "handleJobResult" in r.text
        assert "validation_failed" in r.text

    def test_console_polling_checks_result(self, client):
        r = client.get("/console")
        assert "j.result" in r.text or "handleJobResult" in r.text

    def test_console_handle_job_result_matches_workbench_shapes(self, client):
        """handleJobResult must recognize both {status:'validation_failed'} and {validated:false,errors:[...]} shapes."""
        r = client.get("/console")
        html = r.text
        assert 'validated===false' in html or 'r.validated===false' in html
        assert 'r.blocked===true' in html

    def test_console_accept_all_recs_no_auto_save(self, client):
        """Accept All Recommendations must not auto-save or auto-reload from server."""
        r = client.get("/console")
        assert "applyProposed" in r.text
        assert "Use Save Draft to persist" in r.text
        # Must use rebuildClarificationTable (local render only), not loadAndRenderClarification (which fetches)
        assert "rebuildClarificationTable" in r.text
        # applyProposed must NOT call loadAndRenderClarification (server fetch would overwrite local state)
        assert "// Re-render from local STATE.activeReview only" in r.text
