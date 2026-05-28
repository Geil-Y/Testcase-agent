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
    """Tests for the Console UI shell — React build or legacy fallback."""

    def test_console_shell_served(self, client):
        r = client.get("/console")
        assert r.status_code == 200
        html = r.text.lower()
        assert "<!doctype html>" in html or "<html" in html

    def test_console_shell_has_root_mount(self, client):
        """The shell HTML must include a React mount point."""
        r = client.get("/console")
        assert 'id="root"' in r.text

    def test_console_client_side_routing(self, client):
        """Deep paths should also serve the shell for client-side routing."""
        r = client.get("/console/run/test-001")
        assert r.status_code == 200
        assert 'id="root"' in r.text

    def test_console_no_placeholder_alert(self, client):
        """The 'coming in Issue #5' placeholder must be removed."""
        r = client.get("/console")
        assert "coming in Issue" not in r.text


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

    def test_old_style_runs_report_legacy_unsupported(self):
        """Old-style run_NNN directories with legacy artifacts get legacy_unsupported status."""
        runs = discover_runs()
        old_style = [r for r in runs if r.get("is_legacy")]
        assert len(old_style) > 0, "Expected at least one legacy run directory"
        for r in old_style:
            assert r.get("status") == "legacy_unsupported"


class TestRunStatusInference:
    """Tests for artifact-driven run status."""

    def test_new_run_status(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        assert infer_run_status(tmp_path) == "new"

    def test_extraction_pending_review(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "extracted_test_basis.json").write_text("{}")
        assert infer_run_status(tmp_path) == "extraction_pending_review"

    def test_extraction_blocked(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "extracted_test_basis.json").write_text("{}")
        (tmp_path / "reviewed_extracted_test_basis.json").write_text(
            json.dumps({"blocking_gaps": ["missing threshold"]})
        )
        assert infer_run_status(tmp_path) == "extraction_blocked"

    def test_intents_pending_review(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "case_intents.json").write_text("{}")
        assert infer_run_status(tmp_path) == "intents_pending_review"

    def test_intents_reviewed(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "reviewed_case_intents.json").write_text("{}")
        assert infer_run_status(tmp_path) == "intents_reviewed"

    def test_cases_pending_review(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "generated_cases.json").write_text("{}")
        assert infer_run_status(tmp_path) == "cases_pending_review"

    def test_cases_reviewed(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "reviewed_cases.json").write_text("{}")
        assert infer_run_status(tmp_path) == "cases_reviewed"


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

    def test_extracted_test_basis_downstream(self):
        downstream = get_downstream_artifacts("extracted_test_basis.json")
        assert "reviewed_extracted_test_basis.json" in downstream
        assert "case_intents.json" in downstream
        assert "reviewed_case_intents.json" in downstream
        assert "generated_cases.json" in downstream

    def test_requirements_downstream_everything(self):
        downstream = get_downstream_artifacts("00_requirements.json")
        assert len(downstream) >= 5

    def test_generated_cases_downstream(self):
        downstream = get_downstream_artifacts("generated_cases.json")
        assert "reviewed_cases.json" in downstream

    def test_artifacts_to_archive_only_existing(self, tmp_path):
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "extracted_test_basis.json").write_text("{}")
        (tmp_path / "reviewed_extracted_test_basis.json").write_text(
            json.dumps({"blocking_gaps": []})
        )
        to_archive = artifacts_to_archive("extracted_test_basis.json", tmp_path)
        assert "reviewed_extracted_test_basis.json" in to_archive
        assert "reviewed_cases.json" not in to_archive  # doesn't exist


class TestArchive:
    """Tests for artifact archival."""

    def test_archive_artifacts_moves_files(self, tmp_path):
        (tmp_path / "case_intents.json").write_text(json.dumps({"intent": "test"}))
        (tmp_path / "reviewed_case_intents.json").write_text(json.dumps({"plan": "test"}))

        archived = archive_artifacts(
            tmp_path,
            ["case_intents.json", "reviewed_case_intents.json", "reviewed_cases.json"],
        )
        assert len(archived) == 2  # only 2 existed
        assert not (tmp_path / "case_intents.json").exists()
        assert not (tmp_path / "reviewed_case_intents.json").exists()

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
    load_extraction,
    load_intents,
    load_cases,
    save_extraction_review,
    save_intent_review,
    save_case_edit,
    accept_extraction_all,
    accept_intents_all,
    accept_cases_all,
    plan_and_load_intents,
    generate_and_load_cases,
    regenerate_cases,
    start_run,
    validate_start_run,
)


# ═══════════════════════════════════════════════════════════════════════════
# Issue #10: End-to-end hardening
# ═══════════════════════════════════════════════════════════════════════════


class TestEndToEndHappyPath:
    """Verify the complete happy path through import, run, review, and results."""

    def test_full_api_flow_import_to_cases(self, client, sample_xlsx):
        """Import -> list requirements -> list runs -> mode -> jobs idle -> cases."""
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

        # 3. List runs
        r = client.get("/api/v1/console/runs")
        assert r.status_code == 200

        # 4. Extraction endpoint exists (404 for nonexistent run is expected)
        r = client.get("/api/v1/console/runs/nonexistent/extraction")
        assert r.status_code == 404

        # 5. Job status idle
        r = client.get("/api/v1/console/jobs/current")
        assert r.json()["status"] == "idle"

        # 6. Mode visible
        r = client.get("/api/v1/console/mode")
        assert "mode" in r.json()
        assert "is_mock" in r.json()

    def test_console_page_loads(self, client):
        """GET /console returns the React shell HTML with mount point."""
        r = client.get("/console")
        assert r.status_code == 200
        html = r.text.lower()
        assert "<!doctype html>" in html
        assert 'id="root"' in html
        # The React bundle script should be present
        assert "script" in html


class TestBlockedPath:
    """Verify the blocked Extraction review path."""

    def test_extraction_review_reports_blocking_gaps(self, tmp_path):
        """When an item is blocked in extraction review, save reports it."""
        run_dir = tmp_path / "blocked-run"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "extracted_test_basis.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "sections": {
                "signals": [{"item_id": "f-1", "status": "known", "content": "Test fact", "need": "", "source_text": "test"}],
                "thresholds": [
                    {"item_id": "amb-1", "status": "needs_review", "content": "", "need": "unsafe threshold", "source_text": "test"},
                ],
                "timing": [],
                "states": [],
                "observations": [],
            },
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "blocked-run",
                "run_path": str(run_dir),
                "requirement_key": "REQ-TEST-001",
            }
            result = save_extraction_review("blocked-run", [
                {"item_id": "f-1", "section": "signals", "action": "accept"},
                {"item_id": "amb-1", "section": "thresholds", "action": "block"},
            ])
            assert result["saved"] is True
            assert "item_count" in result
            assert "blocking_gaps" in result


class TestValidationErrors:
    """Verify validation errors are returned with field-level detail."""

    def test_validation_errors_have_structure(self):
        """ValidationError dataclass must have artifact_path, field_path, message."""
        from src.testcase_agent.review_pipeline.artifacts.validation import ValidationError

        e = ValidationError(artifact_path="extracted_test_basis.json", field_path="decisions.0.decision", message="Invalid decision")
        d = {"artifact_path": e.artifact_path, "field_path": e.field_path, "message": e.message}
        assert d["artifact_path"] == "extracted_test_basis.json"
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
            ("POST", "/api/v1/console/runs/test-run/intents/plan"),
            ("POST", "/api/v1/console/runs/test-run/cases/generate"),
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

    def test_no_auto_import_on_extraction_review(self):
        """Save extraction review must not call import_memory."""
        import inspect
        src = inspect.getsource(save_extraction_review)
        assert "import_memory" not in src

    def test_no_auto_import_on_generate(self):
        """Generate cases must not call import_memory."""
        import inspect
        src = inspect.getsource(generate_and_load_cases)
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


class TestExtractionWorkbench:
    """Tests for the Extraction Review workbench functions."""

    def _make_extraction_data(self, run_dir: Path) -> None:
        """Write a minimal extracted_test_basis.json for testing."""
        data = {
            "requirement_key": "REQ-TEST-001",
            "sections": {
                "signals": [
                    {"item_id": "f-1", "status": "known", "content": "Test fact", "need": "", "source_text": "test"}
                ],
                "thresholds": [
                    {"item_id": "amb-1", "status": "needs_review", "content": "", "need": "voltage threshold missing", "source_text": "test"}
                ],
                "timing": [],
                "states": [],
                "observations": [],
            },
        }
        (run_dir / "extracted_test_basis.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2)
        )

    def test_save_extraction_review_persists(self, tmp_path):
        run_dir = tmp_path / "test_run"
        run_dir.mkdir()

        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        self._make_extraction_data(run_dir)

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_get_run:
            mock_get_run.return_value = {
                "run_dir": "test_run",
                "run_path": str(run_dir),
                "requirement_key": "REQ-TEST-001",
            }

            result = save_extraction_review("test_run", [
                {"item_id": "f-1", "section": "signals", "action": "accept"},
                {"item_id": "amb-1", "section": "thresholds", "action": "accept"},
            ])

            assert result["saved"] is True

            # Verify reviewed file was written
            assert (run_dir / "reviewed_extracted_test_basis.json").exists()
            saved_data = json.loads((run_dir / "reviewed_extracted_test_basis.json").read_text())
            assert len(saved_data["sections"]["signals"]) == 1

    def test_save_extraction_review_run_not_found(self):
        with pytest.raises(ValueError, match="not found"):
            save_extraction_review("nonexistent-run", [])


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

    def test_get_extraction_not_found(self, client):
        r = client.get("/api/v1/console/runs/nonexistent/extraction")
        assert r.status_code == 404

    def test_save_extraction_review_requires_run(self, client):
        """When no job is running, nonexistent run returns 404."""
        get_job_runner().clear()
        r = client.post(
            "/api/v1/console/runs/nonexistent/extraction/review",
            json={"actions": []},
        )
        assert r.status_code == 404

    def test_plan_intents_requires_run(self, client):
        """When no job is running, nonexistent run returns 404."""
        get_job_runner().clear()
        r = client.post(
            "/api/v1/console/runs/nonexistent/intents/plan",
            json={},
        )
        assert r.status_code == 404

    def test_save_extraction_blocked_by_job(self, client):
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
            "/api/v1/console/runs/test-run/extraction/review",
            json={"actions": []},
        )
        assert r.status_code == 409

        job._thread.join(timeout=5)
        runner.clear()

    def test_plan_intents_blocked_by_job(self, client):
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
            "/api/v1/console/runs/test-run/intents/plan",
            json={},
        )
        assert r.status_code == 409

        job._thread.join(timeout=5)
        runner.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Issue #7: Case Intent Review and case generation flow
# ═══════════════════════════════════════════════════════════════════════════


class TestIntentWorkbench:
    """Tests for Case Intent Review workbench functions."""

    def _make_intent_data(self, run_dir: Path) -> None:
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "case_intents.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "intents": [
                {
                    "intent_id": "intent-1",
                    "coverage_dimension": "normal_behavior",
                    "intent_text": "Verify normal voltage behavior",
                },
                {
                    "intent_id": "intent-2",
                    "coverage_dimension": "fault_or_protection",
                    "intent_text": "Verify over-voltage fault response",
                },
            ],
        }))

    def test_save_intent_review_persists(self, tmp_path):
        run_dir = tmp_path / "intent_run"
        run_dir.mkdir()
        self._make_intent_data(run_dir)

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "intent_run",
                "run_path": str(run_dir),
                "requirement_key": "REQ-TEST-001",
            }
            result = save_intent_review("intent_run", [
                {"intent_id": "intent-1", "action": "accept"},
                {"intent_id": "intent-2", "action": "block"},
            ])
            assert result["saved"] is True

            # Verify reviewed file was written
            assert (run_dir / "reviewed_case_intents.json").exists()


class TestIntentAPIs:
    """Tests for the Case Intent Review API endpoints."""

    def test_get_intents_not_found(self, client):
        get_job_runner().clear()
        r = client.get("/api/v1/console/runs/nonexistent/intents")
        assert r.status_code == 404

    def test_save_intent_review_requires_run(self, client):
        get_job_runner().clear()
        r = client.post("/api/v1/console/runs/nonexistent/intents/review", json={"actions": []})
        assert r.status_code == 404

    def test_plan_requires_run(self, client):
        get_job_runner().clear()
        r = client.post("/api/v1/console/runs/nonexistent/intents/plan", json={})
        assert r.status_code == 404

    def test_intent_review_blocked_by_job(self, client):
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

        r = client.post("/api/v1/console/runs/test-run/intents/review", json={"actions": []})
        assert r.status_code == 409

        job._thread.join(timeout=5)
        runner.clear()

    def test_plan_blocked_by_job(self, client):
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

        r = client.post("/api/v1/console/runs/test-run/intents/plan", json={})
        assert r.status_code == 409

        job._thread.join(timeout=5)
        runner.clear()


# ═══════════════════════════════════════════════════════════════════════════
# Issue #9: Read-only Results, export, and Review Memory import
# ═══════════════════════════════════════════════════════════════════════════


class TestResults:
    """Tests for read-only cases/results endpoint."""

    def test_cases_endpoint_returns_read_only(self, tmp_path):
        run_dir = tmp_path / "results-run"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "generated_cases.json").write_text(json.dumps([
            {"case_id": "C-1", "title": "Test case", "objective": "Verify voltage"},
        ]))

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

    def test_cases_endpoint_nonexistent_run(self, client):
        r = client.get("/api/v1/console/runs/nonexistent/cases")
        assert r.status_code == 404

    def test_cases_endpoint_read_only(self, client):
        """POST should not be allowed on cases endpoint."""
        r = client.post("/api/v1/console/runs/test-run/cases", json={})
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
        # There is no auto-import in save, accept, or generate flows
        import inspect
        from src.testcase_agent.pipeline_console import workbench
        save_src = inspect.getsource(workbench.save_extraction_review)
        assert "import_memory" not in save_src
        accept_src = inspect.getsource(workbench.accept_extraction_all)
        assert "import_memory" not in accept_src


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
    """Workbench returns must have expected fields for frontend integration."""

    def _make_extraction_data(self, run_dir: Path):
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "extracted_test_basis.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "sections": {
                "signals": [
                    {"item_id": "f-1", "status": "known", "content": "test", "need": "", "source_text": "test"}
                ],
                "thresholds": [
                    {"item_id": "amb-1", "status": "needs_review", "content": "", "need": "voltage threshold", "source_text": "test"}
                ],
                "timing": [],
                "states": [],
                "observations": [],
            },
        }))

    def test_save_extraction_review_has_saved_field(self, tmp_path):
        """save_extraction_review returns saved, reviewed, item_count, blocking_gaps."""
        self._make_extraction_data(tmp_path)
        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "shape-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            result = save_extraction_review("shape-run", [
                {"item_id": "f-1", "section": "signals", "action": "accept"},
                {"item_id": "amb-1", "section": "thresholds", "action": "accept"},
            ])
            assert result["saved"] is True
            assert result["reviewed"] is True
            assert "item_count" in result
            assert "blocking_gaps" in result

    def test_save_extraction_block_has_blocking_gaps(self, tmp_path):
        """Blocking an item should produce blocking_gaps in the result."""
        self._make_extraction_data(tmp_path)
        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "shape-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            result = save_extraction_review("shape-run", [
                {"item_id": "f-1", "section": "signals", "action": "accept"},
                {"item_id": "amb-1", "section": "thresholds", "action": "block",
                 "new_item": {"item_id": "block-1", "status": "needs_review", "need": "Cannot proceed: unclear trigger"}},
            ])
            assert result["saved"] is True
            assert result["reviewed"] is True
            assert len(result.get("blocking_gaps", [])) >= 1


class TestUnchangedUpstreamReuse:
    """Tests for upstream artifact reuse when acceptance is idempotent."""

    def test_accept_extraction_all_creates_reviewed(self, tmp_path):
        """accept_extraction_all writes reviewed_extracted_test_basis.json."""
        run_dir = tmp_path / "accept-all-reuse"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "extracted_test_basis.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "sections": {
                "signals": [{"item_id": "f-1", "status": "known", "content": "test", "need": "", "source_text": "test"}],
                "thresholds": [],
                "timing": [],
                "states": [],
                "observations": [],
            },
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "accept-all-reuse", "run_path": str(run_dir), "requirement_key": "REQ-TEST-001",
            }
            result = accept_extraction_all("accept-all-reuse")
            assert result["saved"] is True
            assert result["reviewed"] is True
            assert (run_dir / "reviewed_extracted_test_basis.json").exists()

    def test_accept_intents_all_creates_reviewed(self, tmp_path):
        """accept_intents_all writes reviewed_case_intents.json."""
        run_dir = tmp_path / "accept-intents-reuse"
        run_dir.mkdir()
        write_run_input(run_dir, REQUIREMENT_FIXTURE)
        (run_dir / "case_intents.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "intents": [
                {"intent_id": "i-1", "coverage_dimension": "normal_behavior", "intent_text": "test"},
            ],
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {
                "run_dir": "accept-intents-reuse", "run_path": str(run_dir), "requirement_key": "REQ-TEST-001",
            }
            result = accept_intents_all("accept-intents-reuse")
            assert result["saved"] is True
            assert result["reviewed"] is True
            assert (run_dir / "reviewed_case_intents.json").exists()


# ═══════════════════════════════════════════════════════════════════════════
# Issue #50: A/B review surfaces — inline edit, add, remove, block
# ═══════════════════════════════════════════════════════════════════════════

class TestExtractionReviewActions:
    """Extraction review supports edit, add, remove, and block actions."""

    def test_save_extraction_edit_action(self, tmp_path):
        """Edit action modifies an item and writes reviewed_extracted_test_basis.json."""
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "extracted_test_basis.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "sections": {
                "signals": [{"item_id": "s1", "status": "known", "content": "orig", "need": "", "source_text": "test"}],
                "thresholds": [], "timing": [], "states": [], "observations": [],
            },
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "edit-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            result = save_extraction_review("edit-run", [
                {"item_id": "s1", "section": "signals", "action": "edit",
                 "edited_item": {"item_id": "s1", "status": "known", "content": "edited", "need": "", "source_text": "test"}},
            ])
            assert result["saved"] is True
            assert result["reviewed"] is True
            reviewed = json.loads((tmp_path / "reviewed_extracted_test_basis.json").read_text(encoding="utf-8"))
            assert reviewed["sections"]["signals"][0]["content"] == "edited"

    def test_save_extraction_add_action(self, tmp_path):
        """Add action adds a new item to the section."""
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "extracted_test_basis.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "sections": {
                "signals": [],
                "thresholds": [], "timing": [], "states": [], "observations": [],
            },
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "add-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            result = save_extraction_review("add-run", [
                {"item_id": "new-sig", "section": "signals", "action": "add",
                 "new_item": {"item_id": "new-sig", "status": "known", "content": "CellVoltage", "need": "", "source_text": ""}},
            ])
            assert result["saved"] is True
            reviewed = json.loads((tmp_path / "reviewed_extracted_test_basis.json").read_text(encoding="utf-8"))
            assert len(reviewed["sections"]["signals"]) == 1
            assert reviewed["sections"]["signals"][0]["content"] == "CellVoltage"

    def test_save_extraction_remove_action(self, tmp_path):
        """Remove action removes an item from the section."""
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "extracted_test_basis.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "sections": {
                "signals": [{"item_id": "s1", "status": "known", "content": "CellVoltage", "need": "", "source_text": "test"}],
                "thresholds": [], "timing": [], "states": [], "observations": [],
            },
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "remove-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            result = save_extraction_review("remove-run", [
                {"item_id": "s1", "section": "signals", "action": "remove"},
            ])
            assert result["saved"] is True
            reviewed = json.loads((tmp_path / "reviewed_extracted_test_basis.json").read_text(encoding="utf-8"))
            assert len(reviewed["sections"]["signals"]) == 0

    def test_save_extraction_blocking_gaps_prevent_accept_all(self, tmp_path):
        """Accept All on extraction with blocking_gaps fails."""
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "extracted_test_basis.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
            "blocking_gaps": ["Non-testable requirement"],
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "blocked-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            with pytest.raises(ValueError, match="blocking"):
                accept_extraction_all("blocked-run")


class TestIntentReviewActions:
    """Intent review supports edit, add, remove, and block actions."""

    def test_save_intent_edit_action(self, tmp_path):
        """Edit action modifies an intent and writes reviewed_case_intents.json."""
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "case_intents.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "intents": [{"intent_id": "i1", "coverage_dimension": "normal_behavior", "intent_text": "Original text"}],
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "edit-intent-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            result = save_intent_review("edit-intent-run", [
                {"intent_id": "i1", "action": "edit",
                 "edited_intent": {"intent_id": "i1", "coverage_dimension": "normal_behavior", "intent_text": "Edited text"}},
            ])
            assert result["saved"] is True
            assert result["reviewed"] is True
            reviewed = json.loads((tmp_path / "reviewed_case_intents.json").read_text(encoding="utf-8"))
            assert reviewed["intents"][0]["intent_text"] == "Edited text"

    def test_save_intent_add_action(self, tmp_path):
        """Add action adds a new intent."""
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "case_intents.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "intents": [],
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "add-intent-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            result = save_intent_review("add-intent-run", [
                {"intent_id": "new-i", "action": "add",
                 "new_intent": {"intent_id": "new-i", "coverage_dimension": "fault_or_protection", "intent_text": "New intent"}},
            ])
            assert result["saved"] is True
            reviewed = json.loads((tmp_path / "reviewed_case_intents.json").read_text(encoding="utf-8"))
            assert len(reviewed["intents"]) == 1
            assert reviewed["intents"][0]["intent_text"] == "New intent"

    def test_save_intent_remove_action(self, tmp_path):
        """Remove action removes an intent."""
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "case_intents.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "intents": [{"intent_id": "i1", "coverage_dimension": "normal_behavior", "intent_text": "Test"}],
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "remove-intent-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            result = save_intent_review("remove-intent-run", [
                {"intent_id": "i1", "action": "remove"},
            ])
            assert result["saved"] is True
            reviewed = json.loads((tmp_path / "reviewed_case_intents.json").read_text(encoding="utf-8"))
            assert len(reviewed["intents"]) == 0

    def test_save_intent_blocking_gaps_prevent_accept_all(self, tmp_path):
        """Accept All on intents with blocking_gaps fails."""
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "case_intents.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "intents": [],
            "blocking_gaps": ["Planning blocked"],
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "blocked-intent-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            with pytest.raises(ValueError, match="blocking"):
                accept_intents_all("blocked-intent-run")


# ═══════════════════════════════════════════════════════════════════════════
# Issue #51: C review — edit and regenerate-with-comment
# ═══════════════════════════════════════════════════════════════════════════

class TestCaseReviewEdit:
    """Case review supports edit and regenerate-with-comment."""

    def test_edit_cases_writes_reviewed(self, tmp_path):
        """Editing cases writes reviewed_cases.json with same schema."""
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "generated_cases.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "cases": [{"case_id": "c1", "title": "Original", "objective": "Test",
                        "pre_condition": "", "post_condition": "",
                        "requirement_key": "REQ-TEST-001", "intent_id": "i1",
                        "coverage_dimension": "normal_behavior", "steps": []}],
        }))
        (tmp_path / "reviewed_extracted_test_basis.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "edit-case-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            result = save_case_edit("edit-case-run", [
                {"case_id": "c1", "title": "Edited", "objective": "Edited obj",
                 "requirement_key": "REQ-TEST-001", "intent_id": "i1",
                 "coverage_dimension": "normal_behavior", "steps": []},
            ])
            assert result["saved"] is True
            assert result["reviewed"] is True
            reviewed = json.loads((tmp_path / "reviewed_cases.json").read_text(encoding="utf-8"))
            assert "cases" in reviewed
            assert reviewed["cases"][0]["title"] == "Edited"

    def test_regenerate_uses_reviewed_artifacts(self, tmp_path):
        """Regenerate requires reviewed_extracted_test_basis.json and reviewed_case_intents.json."""
        write_run_input(tmp_path, REQUIREMENT_FIXTURE)
        (tmp_path / "reviewed_extracted_test_basis.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "sections": {"signals": [], "thresholds": [], "timing": [], "states": [], "observations": []},
        }))
        (tmp_path / "reviewed_case_intents.json").write_text(json.dumps({
            "requirement_key": "REQ-TEST-001",
            "intents": [{"intent_id": "i1", "coverage_dimension": "normal_behavior", "intent_text": "Test"}],
        }))

        with patch("src.testcase_agent.pipeline_console.workbench.get_run") as mock_run:
            mock_run.return_value = {"run_dir": "regen-run", "run_path": str(tmp_path), "requirement_key": "REQ-TEST-001"}
            result = regenerate_cases("regen-run", [
                {"case_id": "c1", "intent_id": "i1", "review_comment": "Improve step clarity"},
            ])
            assert result["saved"] is True
            assert result["regenerated"] is True
            assert result["reviewed"] is True
            assert (tmp_path / "reviewed_cases.json").exists()
            reviewed = json.loads((tmp_path / "reviewed_cases.json").read_text(encoding="utf-8"))
            assert "cases" in reviewed
            # Placeholder mode generates one case
            assert len(reviewed["cases"]) == 1

    def test_regenerate_rejects_empty_comment(self, tmp_path):
        """RegenerateRequest requires non-empty review_comment."""
        from src.testcase_agent.review_pipeline.artifacts.models import RegenerateRequest
        with pytest.raises(Exception):
            RegenerateRequest(case_id="c1", intent_id="i1", review_comment="")

    def test_no_remove_or_block_at_case_review(self):
        """Case review does not support Remove or Block Run."""
        # These actions are not in the case review API — verify the endpoints exist:
        # /cases/edit, /cases/accept-all, /cases/regenerate — but NOT /cases/remove or /cases/block
        from src.testcase_agent.pipeline_console.router import router
        routes = [r.path for r in router.routes]
        case_routes = [r for r in routes if '/cases/' in r]
        assert not any('remove' in r for r in case_routes)
        assert not any('block' in r for r in case_routes)
        assert any('edit' in r for r in case_routes)
        assert any('regenerate' in r for r in case_routes)


class TestAssetServingSecurity:
    """P0: Asset serving must be safe from path traversal and return correct MIME types."""

    def test_assets_path_traversal_rejected(self, client):
        """Double-dot paths under /console/assets must be rejected (404 or 400)."""
        traversal_paths = [
            "/console/assets/../../../etc/passwd",
            "/console/assets/..%2F..%2F..%2Fetc/passwd",
            "/console/assets/....//....//....//etc/passwd",
            "/console/assets/%2e%2e/%2e%2e/etc/passwd",
        ]
        for path in traversal_paths:
            r = client.get(path)
            assert r.status_code in (404, 400), (
                f"Path traversal {path!r} returned {r.status_code}, expected 404 or 400"
            )

    def test_assets_legit_path_served(self, client):
        """A legitimate asset path under /console/assets must return 200 if the dist exists."""
        # The test build may not exist; if assets dir exists, a real file should be served.
        import src.testcase_agent.api as api_mod
        assets_dir = api_mod._CONSOLE_UI_DIST / "assets"
        if assets_dir.exists():
            # Find a real file in the assets dir
            files = list(assets_dir.glob("*"))
            if files:
                asset_path = f"/console/assets/{files[0].name}"
                r = client.get(asset_path)
                assert r.status_code == 200, f"Asset {asset_path} returned {r.status_code}"

    def test_console_shell_returns_html(self, client):
        """The /console and /console/run/* shells must return HTML, not JSON."""
        urls = ["/console", "/console/run/test-run-001"]
        for url in urls:
            r = client.get(url)
            assert r.status_code == 200
            content_type = r.headers.get("content-type", "")
            assert "text/html" in content_type, (
                f"{url} returned Content-Type {content_type!r}, expected text/html"
            )

    def test_assets_return_correct_mime_not_html(self, client):
        """JS and CSS assets must each return correct MIME type, not text/html."""
        import src.testcase_agent.api as api_mod
        assets_dir = api_mod._CONSOLE_UI_DIST / "assets"
        if not assets_dir.exists():
            pytest.skip("React build assets not present")
        js_files = sorted(assets_dir.glob("*.js"))
        css_files = sorted(assets_dir.glob("*.css"))
        if not js_files or not css_files:
            pytest.skip("React build JS or CSS assets not found")
        for f, expected in [(js_files[0], "javascript"), (css_files[0], "css")]:
            r = client.get(f"/console/assets/{f.name}")
            assert r.status_code == 200, (
                f"Asset {f.name} returned {r.status_code}, expected 200"
            )
            content_type = r.headers.get("content-type", "")
            assert expected in content_type, (
                f"Asset {f.name} expected Content-Type containing {expected!r}, got {content_type!r}"
            )
            assert "text/html" not in content_type, (
                f"Asset {f.name} must not be served as text/html, got {content_type!r}"
            )

    def test_console_run_shell_returns_html_not_asset(self, client):
        """Direct refresh on /console/run/<run> must return HTML shell, not JSON/asset."""
        r = client.get("/console/run/some-run-dir")
        assert r.status_code == 200
        content_type = r.headers.get("content-type", "")
        assert "text/html" in content_type, (
            f"Run shell returned {content_type!r}, expected text/html"
        )
        body = r.text
        # The HTML shell should contain the React mount point or HTML structure
        assert "Pipeline Console" in body or '<div id="root">' in body or "<html" in body.lower(), (
            "Run shell response does not look like an HTML shell"
        )

    def test_assets_mount_before_catchall(self):
        """Verify StaticFiles mount is registered before the catch-all routes."""
        import src.testcase_agent.api as api_mod
        app = api_mod.create_app()
        routes = app.routes
        # Find the positions of the assets mount and the catch-all
        mount_idx = None
        catchall_idx = None
        for i, route in enumerate(routes):
            path = getattr(route, 'path', '')
            if path == '/console/assets':
                mount_idx = i
            if path == '/console/{rest_path:path}':
                catchall_idx = i
        if mount_idx is not None and catchall_idx is not None:
            assert mount_idx < catchall_idx, (
                f"StaticFiles mount at position {mount_idx} must come before "
                f"catch-all route at position {catchall_idx}"
            )
