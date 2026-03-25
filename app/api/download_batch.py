from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse, Response

from app.core.logging_setup import get_logger
from app.core.user_friendly_errors import BATCH_DOWNLOAD_NOT_FOUND
from app.services.pdf_batch_processor import resolve_batch_output_download

router = APIRouter()

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _media_type_for_file(path: Path) -> str:
    if path.suffix.lower() == ".xlsx":
        return _XLSX_MEDIA_TYPE
    return "text/plain"


def _resolve_batch_file_or_404(filename: str) -> Path:
    logger = get_logger()
    try:
        return resolve_batch_output_download(filename)
    except FileNotFoundError:
        logger.warning("batch download missing or not found filename=%r", filename)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=BATCH_DOWNLOAD_NOT_FOUND,
        )
    except ValueError:
        logger.warning("batch download invalid filename=%r", filename)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=BATCH_DOWNLOAD_NOT_FOUND,
        )


@router.api_route(
    "/download/batch-output/{filename}",
    methods=["GET", "HEAD"],
    response_model=None,
)
def download_batch_output(filename: str, request: Request) -> FileResponse | Response:
    """
    Download (GET) or verify existence (HEAD) of a file under ``outputs/batch/``.

    Only the basename is accepted; path traversal is rejected.
    """
    path = _resolve_batch_file_or_404(filename)
    if request.method == "HEAD":
        length = path.stat().st_size
        return Response(
            status_code=status.HTTP_200_OK,
            media_type=_media_type_for_file(path),
            headers={
                "Content-Length": str(length),
                "Content-Disposition": f'attachment; filename="{Path(filename).name}"',
            },
        )
    return FileResponse(
        path=str(path),
        filename=Path(filename).name,
        media_type=_media_type_for_file(path),
    )
