from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import JSONResponse

from app.api.models import (
    BatchPdfFailure,
    ProcessBatchAcceptedResponse,
    ProcessBatchRequest,
    ProcessBatchStatusResponse,
)
from app.core.logging_setup import get_logger
from app.core.supported_pdf_categories import (
    batch_no_implemented_parser_message,
    process_batch_unsupported_categories_message,
)
from app.core.user_friendly_errors import BATCH_JOB_NOT_FOUND, PROCESSING_FAILED
from app.services.batch_jobs import (
    create_job,
    get_job,
    mark_completed,
    mark_failed,
    mark_running,
)
from app.services.pdf_batch_processor import run_pdf_batch
from app.services.pdf_category import immediate_subfolder_category
from app.services.parsers import get_parser_for_category
from app.services.upload_jobs import (
    category_for_staging_relative_pdf_path,
    expand_selection_to_staged_pdf_paths,
    filter_pdf_paths_existing_under_staged_dir,
    get_upload_job_dir,
    list_pdf_paths,
)

router = APIRouter()


def _execute_batch_job(
    job_id: str,
    root_folder: str,
    pdf_paths: list[str] | None,
    source_root: str | None = None,
    upload_job_id: str | None = None,
    pdf_category_by_path: dict[str, str] | None = None,
) -> None:
    """Runs in a thread pool (sync def via FastAPI BackgroundTasks)."""
    logger = get_logger()
    mark_running(job_id)
    try:
        subset_cat: dict[str, str] | None = None
        if pdf_category_by_path and pdf_paths:
            subset_cat = {p: pdf_category_by_path[p] for p in pdf_paths}
        output_file, failed_paths, pdf_paths_attempted = run_pdf_batch(
            root_folder=root_folder,
            pdf_paths=pdf_paths,
            source_root=source_root,
            pdf_category_by_path=subset_cat,
        )
    except Exception:
        logger.exception(
            "process-batch job failed job_id=%s root_folder=%r", job_id, root_folder
        )
        mark_failed(job_id, error_detail=PROCESSING_FAILED)
        return

    logger.info("process-batch job done job_id=%s output_file=%s", job_id, output_file)
    basename = Path(output_file).name
    download_url = f"/api/download/batch-output/{basename}"
    mark_completed(
        job_id,
        output_file=output_file,
        download_url=download_url,
        failed_paths=failed_paths,
        pdf_paths_attempted=pdf_paths_attempted,
    )

    # Intentionally do not delete `outputs/uploads/<upload_job_id>/` here.
    # Keeping staged files makes it easier to debug missing-path issues.


def _paths_with_implemented_parser(
    paths: list[str],
    path_category_by_path: dict[str, str],
) -> list[str]:
    return [
        p
        for p in paths
        if get_parser_for_category(path_category_by_path.get(p, "(root)")) is not None
    ]


@router.post("/process-batch")
async def start_process_batch(
    payload: ProcessBatchRequest,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    """
    Accept the batch immediately (HTTP 202) and run ``run_pdf_batch`` in the background.

    Poll ``GET /api/process-batch/status/{job_id}`` until ``status`` is ``completed`` or ``failed``.
    """
    logger = get_logger()
    path_category_by_path: dict[str, str] = {}
    source_root: str | None = None

    if payload.upload_job_id:
        staged_dir = get_upload_job_dir(payload.upload_job_id)
        if staged_dir is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "The upload job id is invalid or has expired. Please upload the folder again."
                ),
            )
        source_root = str(staged_dir)
        if payload.selection and len(payload.selection) > 0:
            spec = [(s.category, list(s.subfolders)) for s in payload.selection]
            pairs, expand_err = expand_selection_to_staged_pdf_paths(staged_dir, spec)
            if expand_err:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=expand_err,
                )
            if not pairs:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "No PDFs matched the selected categories and buckets under this upload. "
                        "Adjust your selection or upload again."
                    ),
                )
            path_category_by_path = dict(pairs)
            raw_paths = [p for p, _ in pairs]
            logger.info(
                "process-batch staged upload via selection upload_job_id=%s paths=%s root_folder=%r",
                payload.upload_job_id,
                len(raw_paths),
                payload.root_folder,
            )
        elif payload.pdf_paths:
            raw_paths = filter_pdf_paths_existing_under_staged_dir(
                staged_dir,
                payload.pdf_paths,
                payload.root_folder,
            )
            if not raw_paths:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "No valid PDF paths matched your request under this upload. "
                        "Refresh the folder or adjust selection and try again."
                    ),
                )
            path_category_by_path = {
                p: category_for_staging_relative_pdf_path(p) for p in raw_paths
            }
            logger.info(
                "process-batch staged upload with client pdf_paths upload_job_id=%s "
                "matched=%s root_folder=%r",
                payload.upload_job_id,
                len(raw_paths),
                payload.root_folder,
            )
        else:
            raw_paths = list_pdf_paths(staged_dir)
            path_category_by_path = {
                p: category_for_staging_relative_pdf_path(p) for p in raw_paths
            }
            logger.info(
                "process-batch using staged upload upload_job_id=%s pdf_paths=%s root_folder=%r",
                payload.upload_job_id,
                len(raw_paths),
                payload.root_folder,
            )
    else:
        raw_paths = list(payload.pdf_paths or [])
        path_category_by_path = {
            p: immediate_subfolder_category(p, payload.root_folder) for p in raw_paths
        }

    paths_to_run = _paths_with_implemented_parser(raw_paths, path_category_by_path)
    if raw_paths and not paths_to_run:
        cats = list(path_category_by_path.values())
        logger.warning(
            "process-batch rejected: no parser for categories in batch root_folder=%r raw_count=%s",
            payload.root_folder,
            len(raw_paths),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                batch_no_implemented_parser_message(cats)
                if cats
                else process_batch_unsupported_categories_message()
            ),
        )

    n_paths = len(paths_to_run)
    logger.info(
        "process-batch accept root_folder=%r pdf_paths_count=%s scheduling_background_job",
        payload.root_folder,
        n_paths,
    )

    job = create_job(payload.root_folder)
    status_url = f"/api/process-batch/status/{job.job_id}"
    background_tasks.add_task(
        _execute_batch_job,
        job.job_id,
        payload.root_folder,
        paths_to_run or None,
        source_root,
        payload.upload_job_id,
        path_category_by_path if path_category_by_path else None,
    )

    logger.info(
        "process-batch accepted job_id=%s root_folder=%r status_url=%s http_status=202",
        job.job_id,
        payload.root_folder,
        status_url,
    )

    body = ProcessBatchAcceptedResponse(
        job_id=job.job_id,
        message=job.message,
        status_url=status_url,
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=body.model_dump(),
    )


@router.get("/process-batch/status/{job_id}", response_model=ProcessBatchStatusResponse)
def process_batch_status(job_id: str) -> ProcessBatchStatusResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=BATCH_JOB_NOT_FOUND,
        )
    failures = [
        BatchPdfFailure(pdf_path=str(row["pdf_path"]), error=str(row["error"]))
        for row in (job.failed_paths or [])
        if isinstance(row, dict) and "pdf_path" in row and "error" in row
    ]
    n_failed = len(failures)
    attempted = getattr(job, "pdf_paths_attempted", 0) or 0
    return ProcessBatchStatusResponse(
        job_id=job.job_id,
        status=job.status,
        message=job.message,
        root_folder=job.root_folder,
        output_file=job.output_file,
        download_url=job.download_url,
        error_detail=job.error_detail,
        failed_paths=failures,
        pdf_paths_attempted=attempted if job.status == "completed" else 0,
        pdf_paths_failed=n_failed if job.status == "completed" else 0,
    )
