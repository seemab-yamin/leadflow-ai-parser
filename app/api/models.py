from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ProcessBatchRequest(BaseModel):
    """Start background batch processing for PDF paths under a logical root folder name."""

    root_folder: str = Field(
        ...,
        min_length=1,
        description=(
            "Folder name from the browser picker (or label for this batch). Used with each "
            "`pdf_path` to determine category (e.g. immediate subfolder like `DC`)."
        ),
    )
    upload_job_id: str | None = Field(
        None,
        description=(
            "If provided, the API will process PDFs staged under "
            "`outputs/uploads/<upload_job_id>/` (uploaded by `POST /api/upload-folder`)."
        ),
    )
    pdf_paths: list[str] | None = Field(
        None,
        description=(
            "Relative or absolute PDF paths on the API server to process. Paths are typically "
            "relative to the server process working directory unless they are absolute and "
            "exist on disk."
        ),
    )

    @field_validator("pdf_paths")
    @classmethod
    def _no_path_traversal_in_pdf_paths(cls, v: list[str] | None) -> list[str] | None:
        if not v:
            return v
        if len(v) > 20_000:
            raise ValueError("Too many pdf_paths (max 20000).")
        for p in v:
            if not isinstance(p, str) or not p.strip():
                raise ValueError("Each path must be a non-empty string.")
            if len(p) > 4096:
                raise ValueError("Path too long.")
            parts = p.replace("\\", "/").split("/")
            if ".." in parts:
                raise ValueError("Paths must not contain '..'.")
        return v

    @field_validator("upload_job_id")
    @classmethod
    def _validate_upload_job_id(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str) or not v.strip():
            raise ValueError("upload_job_id must be a non-empty string.")
        if len(v) > 128:
            raise ValueError("upload_job_id too long.")
        return v.strip()


class BatchPdfFailure(BaseModel):
    """One PDF that could not be processed (e.g. too little text, LLM error)."""

    pdf_path: str
    error: str


class ProcessBatchAcceptedResponse(BaseModel):
    """Returned immediately while `run_pdf_batch` runs in the background."""

    job_id: str
    status: Literal["queued"] = "queued"
    message: str = Field(
        ...,
        description="Human-readable note that work is in progress.",
    )
    status_url: str = Field(
        ...,
        description="Poll this URL until status is completed or failed.",
    )


class ProcessBatchStatusResponse(BaseModel):
    """Current state of a batch job (poll until completed or failed)."""

    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    message: str
    root_folder: str
    output_file: str | None = None
    download_url: str | None = None
    error_detail: str | None = None
    failed_paths: list[BatchPdfFailure] = Field(
        default_factory=list,
        description=(
            "Per-file failures after a completed run (empty while queued/running). "
            "Same rows as the FailedPaths sheet in the downloaded workbook."
        ),
    )
    pdf_paths_attempted: int = Field(
        0,
        ge=0,
        description="Number of PDF paths the batch tried to process (set when status is completed).",
    )
    pdf_paths_failed: int = Field(
        0,
        ge=0,
        description="Count of entries in failed_paths (redundant but convenient for UI).",
    )


class UploadFolderAcceptedResponse(BaseModel):
    """Response from the browser folder upload endpoint."""

    upload_job_id: str
    pdf_paths_saved: int
    staging_dir: str
