from __future__ import annotations

import logging

from config import AppConfig, load_config
from connectors import list_drive_tree


LOGGER = logging.getLogger(__name__)


def bootstrap_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        force=True,
    )


def setup_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def run_pipeline(config: AppConfig) -> None:
    LOGGER.debug("run_pipeline started")
    LOGGER.debug("raw_files_dir=%s", config.raw_files_dir)
    LOGGER.debug("google_drive_root_folder_id=%s", config.google_drive_root_folder_id)

    if config.google_credentials_path is None:
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS is required")

    root_folder_id = config.google_drive_root_folder_id or "root"

    LOGGER.info("Listing Google Drive tree from root folder: %s", root_folder_id)
    drive_items = list_drive_tree(
        credentials_path=config.google_credentials_path,
        root_folder_id=root_folder_id,
    )

    folder_count = sum(1 for item in drive_items if item.is_folder)
    file_count = len(drive_items) - folder_count
    LOGGER.info("Drive scan completed. folders=%s files=%s", folder_count, file_count)

    for item in drive_items[:20]:
        LOGGER.info("[%s] %s", "DIR" if item.is_folder else "FILE", item.path)

    # TODO(2): Download raw PDF files from listed folders.

    # TODO(3): Identify document type from folder name for each downloaded file.
    # TODO(4): Route each file to its matching parser module.
    # TODO(5): Parse extracted fields and normalize records to one schema.
    LOGGER.info("Processing documents")

    # TODO(6): Add Google Sheets connector initialization.
    # TODO(7): Upsert parsed rows into target worksheet.
    # TODO(8): Add basic run summary (files processed, succeeded, failed).
    LOGGER.info("Preparing output for %s", config.google_sheets_worksheet_name)


def execute() -> None:
    # TODO(0): Add argument flags if needed (e.g., dry-run, limit, debug).
    bootstrap_logging()
    LOGGER.debug("execute() entered")

    LOGGER.debug("Loading config from environment")
    config = load_config()
    LOGGER.debug(
        "Config loaded: environment=%s project_name=%s raw_files_dir=%s",
        config.environment,
        config.project_name,
        config.raw_files_dir,
    )
    setup_logging(config.log_level)

    LOGGER.info("Starting %s in %s", config.project_name, config.environment)
    print(
        f"[bootstrap] starting {config.project_name} in {config.environment}",
        flush=True,
    )
    run_pipeline(config)
    LOGGER.info("Pipeline flow completed")


def lambda_handler(event: dict, context: object) -> dict:
    bootstrap_logging()
    LOGGER.debug("lambda_handler invoked")
    LOGGER.debug("event=%s", event)
    LOGGER.debug("context_type=%s", type(context).__name__)

    request_id = getattr(context, "aws_request_id", None)
    function_name = getattr(context, "function_name", None)
    LOGGER.debug("aws_request_id=%s function_name=%s", request_id, function_name)

    try:
        execute()
    except Exception:
        LOGGER.exception("Lambda execution failed")
        raise

    LOGGER.debug("lambda_handler completed successfully")
    return {"status": "ok", "request_id": request_id}
