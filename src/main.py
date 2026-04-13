from __future__ import annotations

import logging

from config import AppConfig, load_config


LOGGER = logging.getLogger(__name__)


def setup_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def run_pipeline(config: AppConfig) -> None:
    # TODO(1): Add Google Drive connector initialization (auth + client setup).
    # TODO(2): List and download raw PDF files from configured Drive folder(s).
    LOGGER.info("Discovering source files in %s", config.raw_files_dir)

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
    config = load_config()
    setup_logging(config.log_level)

    LOGGER.info("Starting %s in %s", config.project_name, config.environment)
    run_pipeline(config)
    LOGGER.info("Pipeline flow completed")


def lambda_handler(event: dict, context: object) -> dict:
    execute()
    return {"status": "ok"}
