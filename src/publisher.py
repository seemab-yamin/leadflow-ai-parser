from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from google.oauth2 import service_account

from config import AppConfig, load_config
from connectors import SQSPublisher, list_directories, list_files
from connectors.google_auth import get_credentials, get_google_drive_service
from logging_setup import bootstrap_logging

LOGGER = logging.getLogger(__name__)

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


class PublisherComponent:
    """Publisher Component

    Trigger: Scheduled (CloudWatch Events) or on-demand

    Responsibilities:
    - Fetch all files from configured Google Drive root folder
    - Filter files based on immediate parent folder name against ENABLED_FOLDERS env var
    - Push each eligible file as separate message to SQS

    Message payload: { "folder_name": string, "file_id": string, "file_name": string,
                       "file_mimeType": string, "timestamp": timestamp }
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self.messages_published = 0
        self.messages_failed = 0
        self._sqs_publisher: SQSPublisher | None = None
        self._google_credentials: service_account.Credentials | None = None
        self._drive_service: Any | None = None

    @property
    def google_credentials(self) -> service_account.Credentials:
        if self._google_credentials is None:
            self._google_credentials = get_credentials(
                self.config, scopes=[DRIVE_READONLY_SCOPE]
            )
        return self._google_credentials

    @property
    def drive_service(self) -> Any:
        if self._drive_service is None:
            self._drive_service = get_google_drive_service(
                credentials=self.google_credentials
            )
        return self._drive_service

    def check_kill_switch(self) -> bool:
        """Check KILL SWITCH env var - when true, skip execution (emergency stop)"""
        return self.config.kill_switch

    def fetch_all_files_from_drive(self) -> dict[str, list[dict[str, Any]]]:
        """Fetch all files from configured Google Drive root folder

        Returns list of file objects with metadata:
        - id: str
        - name: str
        - mimeType: str
        - parents: list[str]
        """

        google_drive_folder_id = self.config.google_drive_folder_id
        directories = list_directories(
            service=self.drive_service,
            folder_id=google_drive_folder_id,
        )

        enabled_folders = {
            folder.strip().lower() for folder in self.config.enabled_folders if folder
        }
        discovered_folder_names = [
            (directory.get("name") or "").strip()
            for directory in directories
            if directory.get("name")
        ]

        LOGGER.info(
            "Configured root folder=%s enabled_folders=%s discovered_directories=%s",
            google_drive_folder_id,
            sorted(enabled_folders),
            discovered_folder_names,
        )

        eligible_directories = [
            directory
            for directory in directories
            if (directory.get("name") or "").strip().lower() in enabled_folders
        ]

        LOGGER.info(
            "Found %d document type directories, %d enabled",
            len(directories),
            len(eligible_directories),
        )

        master_files = {}
        for directory in eligible_directories:
            document_type = (directory.get("name") or "").strip()
            directory_id = directory.get("id")

            if not directory_id:
                LOGGER.warning(
                    "Skipping directory with missing id: name=%s",
                    document_type,
                )
                continue

            document_type_files = list_files(
                service=self.drive_service,
                folder_id=directory_id,
            )

            LOGGER.info(
                "Crawled document_type=%s folder_id=%s files=%d",
                document_type,
                directory_id,
                len(document_type_files),
            )

            master_files[document_type] = document_type_files
        return master_files

    def publish_to_sqs(self, message: dict[str, Any]) -> bool:
        """Push message to SQS queue

        Returns True if successful, False if failed

        Configuration:
        - SQS_QUEUE_URL: Destination queue

        Error Handling:
        - SQS unavailable → retry with backoff
        - Log failures for monitoring
        """
        if not self.config.sqs_queue_url:
            LOGGER.error("SQS_QUEUE_URL is not configured")
            return False

        try:
            if self._sqs_publisher is None:
                self._sqs_publisher = SQSPublisher(queue_url=self.config.sqs_queue_url)

            return self._sqs_publisher.publish_message(message=message)
        except Exception:
            LOGGER.exception("Unexpected error while publishing message to SQS")
            return False

    def publish(self) -> dict[str, Any]:
        """Main publisher execution flow"""
        LOGGER.info("Publisher starting")

        # Check emergency kill switch
        if self.check_kill_switch():
            LOGGER.warning("KILL SWITCH is enabled - publisher skipping execution")
            return {
                "status": "skipped",
                "reason": "kill switch_enabled",
                "messages_published": 0,
                "messages_failed": 0,
            }

        LOGGER.info("Google credentials validated successfully")
        # Validate SQS queue is configured
        if not self.config.sqs_queue_url:
            LOGGER.error("SQS_QUEUE_URL not configured - cannot publish messages")
            return {
                "status": "error",
                "reason": "sqs_queue_url_missing",
                "messages_published": 0,
                "messages_failed": 0,
            }

        # Fetch all files from Google Drive grouped by document_type
        LOGGER.info("Fetching all files from Google Drive root folder")
        all_files_by_type = self.fetch_all_files_from_drive()
        total_files = sum(len(files) for files in all_files_by_type.values())
        LOGGER.info(
            "Fetched %d files across %d document types from Google Drive",
            total_files,
            len(all_files_by_type),
        )

        # If no files, graceful exit
        if total_files == 0:
            LOGGER.info("No files found in Google Drive - graceful exit")
            return {
                "status": "ok",
                "reason": "no_files_found",
                "messages_published": 0,
                "messages_failed": 0,
            }

        messages = []
        for document_type, files in all_files_by_type.items():
            for file_obj in files:
                messages.append(
                    {
                        "id": file_obj.get("id", ""),
                        "name": file_obj.get("name", ""),
                        "mimeType": file_obj.get("mimeType", ""),
                        "parents": file_obj.get("parents") or [],
                        "document_type": document_type,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

        if self._sqs_publisher is None:
            self._sqs_publisher = SQSPublisher(queue_url=self.config.sqs_queue_url)

        LOGGER.info(
            "Publishing %d messages in batches of %d",
            len(messages),
            self.config.sqs_publish_batch_size,
        )

        batch_successful_count, failed_messages = self._sqs_publisher.publish_batch(
            messages=messages,
            batch_size=self.config.sqs_publish_batch_size,
        )
        self.messages_published += batch_successful_count

        if failed_messages:
            LOGGER.warning(
                "Resending %d failed batch messages individually",
                len(failed_messages),
            )

        for failed_message in failed_messages:
            if self.publish_to_sqs(failed_message):
                self.messages_published += 1
                LOGGER.info(
                    "Published previously failed batch message for file_id=%s",
                    failed_message.get("id"),
                )
            else:
                self.messages_failed += 1
                LOGGER.error(
                    "Failed to republish batch message for file_id=%s",
                    failed_message.get("id"),
                )

        LOGGER.info(
            "Publisher completed. published=%d failed=%d",
            self.messages_published,
            self.messages_failed,
        )

        return {
            "status": "ok" if self.messages_failed == 0 else "partial_failure",
            "messages_published": self.messages_published,
            "messages_failed": self.messages_failed,
            "total_messages": self.messages_published + self.messages_failed,
        }


def lambda_handler(event: dict, context: object) -> dict:
    config = load_config()
    bootstrap_logging(config.log_level.upper())
    request_id = getattr(context, "aws_request_id", None)

    try:
        LOGGER.info("Starting %s in %s", config.project_name, config.environment)
        publisher = PublisherComponent(config)
        result = publisher.publish()
        LOGGER.info("Pipeline flow completed")
    except Exception:
        LOGGER.exception("Publisher execution failed")
        raise

    return {
        "status": result.get("status"),
        "request_id": request_id,
        "messages_published": result.get("messages_published", 0),
        "messages_failed": result.get("messages_failed", 0),
    }
