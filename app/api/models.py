from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CategoryBucketSelection(BaseModel):
    """
    User-chosen buckets (immediate subfolders) under one **category folder**.

    See ``app.core.batch_selection_contract`` for vocabulary.
    """

    category: str = Field(
        ...,
        min_length=1,
        max_length=512,
        description="Immediate child of the picked root (e.g. DC, VA Alexandria).",
    )
    subfolders: list[str] = Field(
        ...,
        min_length=1,
        description=(
            "Immediate subfolder names under this category to include. Use an empty string "
            '`""` for PDFs placed directly in the category folder (not inside a subfolder).'
        ),
    )

    @field_validator("category")
    @classmethod
    def _category_trim(cls, v: str) -> str:
        s = str(v).strip()
        if not s:
            raise ValueError("category must be non-empty.")
        if "/" in s or "\\" in s or ".." in s:
            raise ValueError("category must be a single path segment.")
        return s

    @field_validator("subfolders")
    @classmethod
    def _subfolders_clean(cls, v: list[str]) -> list[str]:
        if len(v) > 20_000:
            raise ValueError("Too many subfolders (max 20000).")
        out: list[str] = []
        for raw in v:
            # Allow `""` after strip only when raw is literally empty / whitespace (direct bucket).
            if raw is None:
                raise ValueError("subfolder name must be a string.")
            if isinstance(raw, str) and raw.strip() == "":
                out.append("")
                continue
            s = str(raw).strip()
            if len(s) > 512:
                raise ValueError("Subfolder name too long.")
            if "/" in s or "\\" in s or ".." in s:
                raise ValueError("subfolders must be single path segments.")
            out.append(s)
        return out


class ProcessBatchRequest(BaseModel):
    """Start background batch processing for PDF paths under a logical root folder name."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "summary": "Browser + staged upload (preferred)",
                    "value": {
                        "root_folder": "My Matter",
                        "upload_job_id": "f2c0b7e4a1d34a6c9e8b0d1e2f3a4b5c",
                        "selection": [
                            {"category": "DC", "subfolders": ["", "2026"]},
                            {"category": "VA Alexandria", "subfolders": ["Circuit"]},
                        ],
                    },
                },
                {
                    "summary": "Server cwd only (no upload)",
                    "value": {
                        "root_folder": "batch-root",
                        "pdf_paths": ["DC/case.pdf"],
                    },
                },
            ]
        }
    )

    root_folder: str = Field(
        ...,
        min_length=1,
        description=(
            "Folder name from the browser picker (or label for this batch). With staged "
            "``upload_job_id`` + ``selection``, parser category comes from each selection "
            "entry, not from re-parsing paths. For cwd-only batches, category is inferred "
            "from each ``pdf_path`` under this root name."
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
            "PDF paths on the API host: either relative to the process working directory "
            "(no ``upload_job_id``), or validated under a staged upload when sent with "
            "``upload_job_id`` and **without** ``selection`` (legacy/script use)."
        ),
    )
    selection: list[CategoryBucketSelection] | None = Field(
        None,
        description=(
            "Per-category bucket picks for staged uploads. When non-empty, the server expands "
            "these to PDF paths under ``outputs/uploads/<upload_job_id>/`` and ignores "
            "``pdf_paths`` for that job. Requires ``upload_job_id``. See ``batch_selection_contract``."
        ),
    )

    @model_validator(mode="after")
    def _selection_requires_upload_job(self) -> ProcessBatchRequest:
        if self.selection and len(self.selection) > 0 and not self.upload_job_id:
            raise ValueError("selection requires upload_job_id for staged expansion.")
        return self

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
