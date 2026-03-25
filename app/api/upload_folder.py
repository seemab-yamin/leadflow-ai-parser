from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.models import UploadFolderAcceptedResponse
from app.core.logging_setup import get_logger
from app.services.upload_jobs import (
    create_upload_job_dir,
    delete_upload_job_dir,
    save_uploaded_folder_files,
)

router = APIRouter()
logger = get_logger()


@router.post(
    "/upload-folder",
    response_model=UploadFolderAcceptedResponse,
    status_code=status.HTTP_200_OK,
)
async def upload_folder(
    *,
    root_folder_name: str = Form(..., min_length=1),
    files: list[UploadFile] = File(...),
) -> UploadFolderAcceptedResponse:
    """
    Upload PDFs from the browser folder picker and stage them server-side.

    The browser should send `files` with their original relative path as the multipart
    filename (e.g. `MyFolder/DC/file.pdf`). We strip the top-level picker root
    (`root_folder_name`) and save into:

      outputs/uploads/<upload_job_id>/<relative path after root stripping>
    """
    upload_job_id, job_dir = create_upload_job_dir()
    try:
        saved_pdf_paths = await save_uploaded_folder_files(
            job_dir=job_dir,
            root_folder_name=root_folder_name,
            files=files,
        )
    except Exception as exc:
        logger.exception("upload-folder failed upload_job_id=%s", upload_job_id)
        delete_upload_job_dir(upload_job_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    logger.info(
        "upload-folder staged upload_job_id=%s root_folder_name=%s saved_pdf_paths=%s job_dir=%s",
        upload_job_id,
        root_folder_name,
        len(saved_pdf_paths),
        str(job_dir),
    )

    return UploadFolderAcceptedResponse(
        upload_job_id=upload_job_id,
        pdf_paths_saved=len(saved_pdf_paths),
        staging_dir=str(job_dir),
    )

