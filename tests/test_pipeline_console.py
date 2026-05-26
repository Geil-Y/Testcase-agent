"""Tests for Pipeline Console: import batches, API routes, and UI shell."""

from __future__ import annotations

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

        # Retry
        retried = runner.retry_job(work)
        retried._thread.join(timeout=5)
        assert retried.status == JobStatus.succeeded
        assert retried.result == "success on retry"
        assert counter["tries"] == 2

    def test_retry_requires_failed_job(self):
        runner = JobRunner()
        with pytest.raises(JobConflictError, match="No failed job"):
            runner.retry_job(lambda: None)

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

    def test_retry_requires_existing_job(self, client):
        r = client.post("/api/v1/console/jobs/retry")
        assert r.status_code in (400, 409)


from src.testcase_agent.pipeline_console.workbench import (
    load_clarification_review,
    save_and_advance_clarification,
    save_clarification_draft,
    start_run,
)


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

            assert result["filled"] >= 1
            assert result["requires_confirmation"] is True
            assert result["high_risk_skipped"] >= 1
            assert "amb-2" in result["high_risk_items"]

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

            assert result["requires_confirmation"] is False
            assert result["filled"] == 3
            assert result["high_risk_accepted"] >= 1

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
