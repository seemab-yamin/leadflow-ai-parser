"""
In-memory batch job registry for async `run_pdf_batch` execution.

Replace with Redis / a task queue when you need multiple workers or persistence.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

JobStatus = Literal["queued", "running", "completed", "failed"]


@dataclass
class BatchJob:
    job_id: str
    root_folder: str
    status: JobStatus = "queued"
    message: str = "Your batch is queued and will start shortly."
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    output_file: str | None = None
    download_url: str | None = None
    error_detail: str | None = None
    failed_paths: list[dict] = field(default_factory=list)
    pdf_paths_attempted: int = 0


_lock = threading.Lock()
_jobs: dict[str, BatchJob] = {}


def create_job(root_folder: str) -> BatchJob:
    job_id = uuid.uuid4().hex
    job = BatchJob(job_id=job_id, root_folder=root_folder)
    with _lock:
        _jobs[job_id] = job
    return job


def get_job(job_id: str) -> BatchJob | None:
    with _lock:
        return _jobs.get(job_id)


def mark_running(job_id: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "running"
        job.message = "Processing your PDF batch — this may take a while."
        job.updated_at = datetime.now(timezone.utc)


def mark_completed(
    job_id: str,
    *,
    output_file: str,
    download_url: str,
    failed_paths: list[dict] | None = None,
    pdf_paths_attempted: int = 0,
) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "completed"
        n_fail = len(failed_paths or [])
        if n_fail > 0:
            job.message = (
                f"Processing finished with {n_fail} file(s) that could not be processed. "
                "Review the errors below before opening the spreadsheet."
            )
        else:
            job.message = "Processing finished. You can download your output file."
        job.output_file = output_file
        job.download_url = download_url
        job.failed_paths = list(failed_paths or [])
        job.pdf_paths_attempted = max(0, int(pdf_paths_attempted))
        job.updated_at = datetime.now(timezone.utc)


def mark_failed(job_id: str, *, error_detail: str) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "failed"
        job.message = (
            "Processing failed. Try again or contact support if it keeps happening."
        )
        job.error_detail = error_detail
        job.updated_at = datetime.now(timezone.utc)
