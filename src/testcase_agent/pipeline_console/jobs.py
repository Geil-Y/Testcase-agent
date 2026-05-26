"""Local in-memory job runner for pipeline Console long-running actions."""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


@dataclass
class Job:
    id: str
    name: str
    status: JobStatus = JobStatus.queued
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: Any = None
    error: str | None = None
    error_detail: str | None = None
    run_dir: str | None = None
    _thread: threading.Thread | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "has_result": self.result is not None,
            "error": self.error,
            "error_detail": self.error_detail,
            "run_dir": self.run_dir,
        }


class JobRunner:
    """Single-job, in-memory runner for local Console MVP.

    Only one job can run at a time. Editing and stage actions are rejected
    while a job is running.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current_job: Job | None = None
        self._history: list[Job] = []

    # -- public API ----------------------------------------------------------

    def create_job(self, name: str, run_dir: str | None = None) -> Job:
        """Create a new job. Rejects if another job is already running."""
        with self._lock:
            if self._current_job and self._current_job.status == JobStatus.running:
                raise JobConflictError(
                    f"A job is already running: {self._current_job.name} "
                    f"(id={self._current_job.id})"
                )
            job = Job(
                id=uuid.uuid4().hex[:12],
                name=name,
                run_dir=run_dir,
            )
            self._current_job = job
            self._history.append(job)
            return job

    def start_job(self, job: Job, fn: Callable[[], Any]) -> None:
        """Execute fn in a background thread, updating job status."""
        job.status = JobStatus.running
        job.started_at = time.time()

        def _run() -> None:
            try:
                result = fn()
                job.result = result
                job.status = JobStatus.succeeded
            except Exception as e:
                job.error = str(e)
                job.error_detail = traceback.format_exc()
                job.status = JobStatus.failed
            finally:
                job.finished_at = time.time()

        job._thread = threading.Thread(target=_run, daemon=True)
        job._thread.start()

    def get_job(self) -> dict[str, Any] | None:
        """Get the current job status, or None if idle."""
        if self._current_job is None:
            return None
        return self._current_job.to_dict()

    def is_running(self) -> bool:
        """Check if a job is currently running."""
        if self._current_job is None:
            return False
        return self._current_job.status == JobStatus.running

    def retry_job(self, fn: Callable[[], Any]) -> Job:
        """Retry the last failed job. Requires no running job."""
        with self._lock:
            if self._current_job is None or self._current_job.status != JobStatus.failed:
                raise JobConflictError("No failed job to retry")
            if self.is_running():
                raise JobConflictError("A job is already running")
            job = self._current_job
            job.error = None
            job.error_detail = None
            job.result = None
        self.start_job(job, fn)
        return job

    def clear(self) -> None:
        """Clear the current job (allow next job)."""
        self._current_job = None


class JobConflictError(Exception):
    """Raised when a job operation conflicts with the current job state."""
    pass


# Global singleton for the app lifetime
_runner: JobRunner | None = None


def get_job_runner() -> JobRunner:
    global _runner
    if _runner is None:
        _runner = JobRunner()
    return _runner
