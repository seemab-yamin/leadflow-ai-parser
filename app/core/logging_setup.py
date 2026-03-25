import logging
import uuid
from pathlib import Path
from time import monotonic

from fastapi import Request
from starlette.responses import Response
from typing import Callable

from app.core.config import settings

from logging.handlers import RotatingFileHandler


def get_logger() -> logging.Logger:
    """Project-standard logger name for consistent file logging."""
    return logging.getLogger("leadfflow")


def _resolve_level() -> int:
    if settings.log_level:
        level_map = logging.getLevelNamesMapping()
        return level_map.get(settings.log_level.upper(), logging.INFO)
    return logging.DEBUG if settings.app_env == "dev" else logging.INFO


def configure_logging() -> None:
    """
    Configure a single shared file logger in `logs-dir/`.

    This is designed to be idempotent so it won't duplicate handlers during
    `uvicorn --reload` restarts/reloader spins.
    """

    root_logger = logging.getLogger()
    root_level = _resolve_level()
    root_logger.setLevel(root_level)

    repo_root = Path(__file__).resolve().parents[2]
    logs_dir = repo_root / settings.log_dir
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_file = logs_dir / "app.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler (dedupe by filename).
    existing_files = {
        getattr(h, "baseFilename", None)
        for h in root_logger.handlers
        if hasattr(h, "baseFilename")
    }
    if str(log_file) not in existing_files:
        file_handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=settings.log_max_bytes,
            backupCount=settings.log_backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Ensure our application logger exists with stable defaults.
    lead_logger = get_logger()
    lead_logger.setLevel(root_level)
    # Keep it from creating a second copy; rely on propagation to root.
    lead_logger.propagate = True


def request_id_header() -> str:
    return str(uuid.uuid4())


async def http_request_logging_middleware(request: Request, call_next: Callable) -> Response:
    """
    FastAPI/Starlette middleware for logging requests + duration.

    Notes:
    - Uses root logger handlers configured by `configure_logging()`.
    - Adds `X-Request-ID` to the response when possible.
    """

    logger = get_logger()
    req_id = request.headers.get("x-request-id") or request_id_header()
    start = monotonic()

    try:
        response = await call_next(request)
        duration_ms = (monotonic() - start) * 1000
        response.headers["X-Request-ID"] = req_id
        logger.info(
            "request_id=%s method=%s path=%s status_code=%s duration_ms=%.2f",
            req_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
    except Exception:
        duration_ms = (monotonic() - start) * 1000
        logger.exception(
            "request_id=%s method=%s path=%s duration_ms=%.2f unhandled_exception",
            req_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

