from __future__ import annotations

import copy
import io
import json
import logging
import os
import re
from typing import Any, Callable

from google.oauth2 import service_account
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from config import AppConfig, load_config
from connectors.google_auth import (
    get_credentials,
    get_google_drive_service,
    get_google_sheets_service,
)
from connectors.llm import llm_call
from logging_setup import bootstrap_logging
from parsers.pdf.factory import get_pdf_parser

LOGGER = logging.getLogger(__name__)
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]

GOOGLE_SHEET_HEADERS: dict[str, list[str]] = {}


def _name_key(person: dict) -> str:
    """Deduplication key: First+Last names (case-insensitive)."""
    first = str(person.get("First Name") or "").strip().casefold()
    last = str(person.get("Last Name") or "").strip().casefold()
    return f"{first}::{last}"


def _has_address(person: dict) -> bool:
    """Whether this record contains an address-like value."""
    addr = str(person.get("Address") or "").strip()
    return bool(addr)


def _merge_person_with_address(base: dict, other: dict) -> dict:
    """Merge two person dicts, filling only empty fields from `other`."""
    merged = dict(base)
    for k, v in other.items():
        if merged.get(k) not in (None, ""):
            continue
        if v not in (None, ""):
            merged[k] = v
    return merged


def _build_all_parties(
    party_data: list[dict],
    heirs: list[dict],
    max_heirs: int = 2,
) -> list[dict]:
    """
    Build deduplicated all_parties from party arrays + up to max_heirs heirs.
    When duplicate found (same First+Last name), prefer the one with address as owner.
    """
    all_parties: list[dict] = []
    seen: dict[str, int] = {}  # name_key -> index in all_parties

    for party in party_data:
        key = _name_key(party)
        if key not in seen:
            seen[key] = len(all_parties)
            all_parties.append(party)
        else:
            idx = seen[key]
            existing = all_parties[idx]
            if _has_address(party) and not _has_address(existing):
                all_parties[idx] = party
            elif _has_address(existing) and not _has_address(party):
                all_parties[idx] = _merge_person_with_address(existing, party)
            else:
                all_parties[idx] = _merge_person_with_address(existing, party)

    heirs_added = 0
    for heir in heirs:
        if heirs_added >= max_heirs:
            break
        key = _name_key(heir)
        if key not in seen:
            seen[key] = len(all_parties)
            all_parties.append(heir)
            heirs_added += 1
        else:
            idx = seen[key]
            existing = all_parties[idx]
            if _has_address(heir) and not _has_address(existing):
                all_parties[idx] = heir
            elif _has_address(existing) and not _has_address(heir):
                all_parties[idx] = _merge_person_with_address(existing, heir)
            else:
                all_parties[idx] = _merge_person_with_address(existing, heir)

    return all_parties


def _clean_phone_number(value: str | None) -> str | None:
    if value is None:
        return None
    s = re.sub(r"\D+", "", str(value))
    if not s:
        return None
    if len(s) == 11 and s.startswith("1"):
        s = s[1:]
    return s


def _is_retryable_google_error(exception: Exception) -> bool:
    """Return True if the exception is a retryable Google API error (e.g. 429, 5xx)."""
    if isinstance(exception, HttpError):
        # Retry on Rate Limit (429) or Server Errors (5xx)
        return exception.resp.status == 429 or exception.resp.status >= 500
    return False


class ConsumerComponent:
    """Consumer Component

    Trigger: SQS message event

    Responsibilities:
    - Receive file metadata from SQS
    - Fetch file content from Google Drive
    - Run pre/post processing and LLM-based processing
    - Move processed files to their destination folder
    """

    def __init__(self, config: AppConfig):
        self.config = config
        self._google_credentials: service_account.Credentials | None = None
        self._drive_service: Any | None = None
        self._google_sheets_service: Any | None = None

    @property
    def google_credentials(self) -> service_account.Credentials:
        if self._google_credentials is None:
            self._google_credentials = get_credentials(self.config, scopes=SCOPES)
        return self._google_credentials

    @property
    def drive_service(self) -> Any:
        if self._drive_service is None:
            self._drive_service = get_google_drive_service(
                credentials=self.google_credentials
            )
        return self._drive_service

    @property
    def google_sheets_service(self) -> Any:
        if self._google_sheets_service is None:
            self._google_sheets_service = get_google_sheets_service(
                credentials=self.google_credentials
            )
        return self._google_sheets_service

    def check_kill_switch(self) -> bool:
        """Check KILL_SWITCH env var - when true, skip consumer execution."""
        return self.config.kill_switch

    def parse_message(self, message_body: Any) -> dict[str, Any]:
        """Parse the SQS message body into a file-metadata dictionary.

        Expected keys:
        - id
        - name
        - mimeType
        - parents
        - document_type
        - timestamp
        """
        if isinstance(message_body, str):
            try:
                parsed_message = json.loads(message_body)
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid JSON in SQS message body") from exc
        elif isinstance(message_body, dict):
            parsed_message = message_body
        else:
            raise ValueError("Unsupported SQS message body type")

        required_keys = ("id", "name", "mimeType", "parents", "document_type")
        missing_keys = [key for key in required_keys if key not in parsed_message]
        if missing_keys:
            raise ValueError(
                f"SQS message missing required keys: {', '.join(missing_keys)}"
            )

        return parsed_message

    def determine_document_type(self, message: dict[str, Any]) -> str:
        """Determine document type from message metadata."""
        document_type = (
            (message.get("document_type") or "").strip().replace(" ", "_").upper()
        )
        if not document_type:
            raise ValueError("Missing document_type in message")
        return document_type

    def get_prompt_for_document_type(self, document_type: str) -> str:
        """Resolve prompt text by reading the .txt file specified in environment.
        Example for DC:
          1. reads `DC_PROMPT` env var (e.g. "DC_Prob_Prompt_v7.txt")
          2. joins with `config.prompts_dir`
          3. reads and returns file content
        """
        env_key = f"{document_type}_PROMPT"
        prompt_filename = os.getenv(env_key)
        if not prompt_filename:
            raise ValueError(f"Missing prompt filename environment variable: {env_key}")

        prompt_path = self.config.prompts_dir / prompt_filename
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found at: {prompt_path}")

        try:
            return prompt_path.read_text(encoding="utf-8")
        except Exception as exc:
            LOGGER.error(f"Failed to read prompt file {prompt_path}: {str(exc)}")
            raise

    def dc_preprocessing_function(self, content: bytes) -> str:
        """DC-specific preprocessing placeholder."""
        # Implement DC preprocessing (OCR/text extraction/cleanup).
        text = get_pdf_parser("tika").extract_text(content)
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r" +", " ", text)
        lines = [
            line for line in text.split("\n") if "Register of Actions -" not in line
        ]
        return "\n".join(lines).strip()

    def va_alexandria_preprocessing_function(self, content: bytes) -> str:
        """VA_ALEXANDRIA-specific preprocessing placeholder."""
        # Implement VA_ALEXANDRIA preprocessing (OCR/text extraction/cleanup).
        text = get_pdf_parser("docling").extract_text(content)
        lines = text.split("\n")
        result: list[str] = []
        url_pattern = re.compile(r"https?://\S+")

        # Only match timestamp format (DD/MM/YYYY, HH:MM) - not bare dates like 08/12/2025.
        # Header/footer "printed on" stamps include time.
        timestamp_pattern = re.compile(
            r"^\s*\d{1,2}/\d{1,2}/\d{4}\s*,\s*\d{1,2}:\d{2}\s*$"
        )
        page_num_pattern = re.compile(r"^\s*\d+/\d+\s*$")

        for line in lines:
            line = url_pattern.sub("", line).strip()
            if timestamp_pattern.match(line) or page_num_pattern.match(line):
                continue
            if not line:
                continue
            result.append(line)

        # Preserve line breaks for better downstream matching.
        return "\n".join(result).strip()

    def dc_postprocessing_function(
        self, llm_output: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """DC-specific postprocessing placeholder."""
        # Pop party arrays and Heirs - expand into one record per party
        party_keys = (
            "Applicants",
            "Administrator",
            "POW",
            "Subscriber",
            "Executor",
            "Personal Representative",
        )
        all_parties: list[dict] = []
        for key in party_keys:
            items = llm_output.pop(key, [])
            if isinstance(items, list):
                all_parties.extend(items)
        heirs = llm_output.pop("Heirs", [])
        if not isinstance(heirs, list):
            heirs = []

        # Add Heir columns to base llm_output (each record inherits these)
        for i, hr in enumerate(heirs):
            if not isinstance(hr, dict):
                continue
            llm_output[f"Heir {i + 1} First Name"] = hr.get("First Name")
            llm_output[f"Heir {i + 1} Last Name"] = hr.get("Last Name")
            llm_output[f"Relationship {i + 1}"] = hr.get("Relationship")
            llm_output[f"Age {i + 1}"] = hr.get("Age")
            llm_output[f"Address {i + 1}"] = hr.get("Address")
            llm_output[f"City {i + 1}"] = hr.get("City")
            llm_output[f"State {i + 1}"] = hr.get("State")
            llm_output[f"Zip {i + 1}"] = hr.get("Zip")

        records: list[dict] = []
        if all_parties:
            for party in all_parties:
                if not isinstance(party, dict):
                    continue
                record = copy.deepcopy(llm_output)
                record["Owner 1 First Name"] = party.get("First Name")
                record["Owner 1 Last Name"] = party.get("Last Name")
                record["Owner 2 First Name"] = None
                record["Owner 2 Last Name"] = None
                record["Property Address Line 1"] = party.get("Address")
                record["Property Address Line 2"] = None
                record["Property City"] = party.get("City")
                record["Property State"] = party.get("State")
                record["Property ZIP"] = party.get("Zip")
                record["PR Phone Number"] = _clean_phone_number(
                    party.get("Phone Number")
                )
                records.append(record)
        else:
            # No parties: create one record with null owner/property fields
            record = copy.deepcopy(llm_output)
            record["Owner 1 First Name"] = None
            record["Owner 1 Last Name"] = None
            record["Owner 2 First Name"] = None
            record["Owner 2 Last Name"] = None
            record["Property Address Line 1"] = None
            record["Property Address Line 2"] = None
            record["Property City"] = None
            record["Property State"] = None
            record["Property ZIP"] = None
            record["PR Phone Number"] = None
            records.append(record)
        return records

    def va_alexandria_postprocessing_function(
        self, llm_output: dict[str, Any]
    ) -> list[dict[str, Any]]:

        data = dict(llm_output)  # shallow copy to pop from

        party_keys = (
            "Applicants",
            "Administrator",
            "POW",
            "Proponent of Will",
            "Subscriber",
            "Executor",
            "Personal Representative",
        )

        party_data: list[dict] = []
        for key in party_keys:
            items = data.pop(key, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        party_data.append(item)

        heirs = data.pop("Heirs", [])
        if not isinstance(heirs, list):
            heirs = []

        max_heirs = 2

        # Add Heir columns to base data (each record will inherit these) - heirs logic unchanged.
        for i, hr in enumerate(heirs[:max_heirs]):
            if not isinstance(hr, dict):
                continue
            data[f"Heir {i + 1} First Name"] = hr.get("First Name")
            data[f"Heir {i + 1} Last Name"] = hr.get("Last Name")
            data[f"Relationship {i + 1}"] = hr.get("Relationship")
            data[f"Age {i + 1}"] = hr.get("Age")
            data[f"Address {i + 1}"] = hr.get("Address")
            data[f"City {i + 1}"] = hr.get("City")
            data[f"State {i + 1}"] = hr.get("State")
            data[f"Zip {i + 1}"] = hr.get("Zip")

        # Build all_parties with deduplication: add up to 2 heirs, prefer record with address when duplicate.
        all_parties = _build_all_parties(party_data, heirs, max_heirs=max_heirs)

        records: list[dict] = []
        if all_parties:
            for party in all_parties:
                record = copy.deepcopy(data)
                record["Owner 1 First Name"] = party.get("First Name")
                record["Owner 1 Last Name"] = party.get("Last Name")
                record["Owner 2 First Name"] = None
                record["Owner 2 Last Name"] = None
                record["Property Address Line 1"] = party.get("Address")
                record["Property Address Line 2"] = None
                record["Property City"] = party.get("City")
                record["Property State"] = party.get("State")
                record["Property ZIP"] = party.get("Zip")
                record["PR Phone Number"] = _clean_phone_number(
                    party.get("Phone Number")
                )
                records.append(record)
        else:
            # No parties: create one record with null owner/property fields
            record = copy.deepcopy(data)
            record["Owner 1 First Name"] = None
            record["Owner 1 Last Name"] = None
            record["Owner 2 First Name"] = None
            record["Owner 2 Last Name"] = None
            record["Property Address Line 1"] = None
            record["Property Address Line 2"] = None
            record["Property City"] = None
            record["Property State"] = None
            record["Property ZIP"] = None
            record["PR Phone Number"] = None
            records.append(record)

        return records

    def get_preprocessing_function(self, document_type: str) -> Callable[[bytes], str]:
        """Return preprocessing function by document type."""
        preprocessors: dict[str, Callable[[bytes], str]] = {
            "DC": self.dc_preprocessing_function,
            "VA_ALEXANDRIA": self.va_alexandria_preprocessing_function,
        }
        if document_type not in preprocessors:
            raise ValueError(
                f"Unsupported document_type for preprocessing: {document_type}"
            )
        return preprocessors[document_type]

    def get_postprocessing_function(
        self, document_type: str
    ) -> Callable[[dict[str, Any]], dict[str, Any]]:
        """Return postprocessing function by document type."""
        post_processors: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "DC": self.dc_postprocessing_function,
            "VA_ALEXANDRIA": self.va_alexandria_postprocessing_function,
        }
        if document_type not in post_processors:
            raise ValueError(
                f"Unsupported document_type for postprocessing: {document_type}"
            )
        return post_processors[document_type]

    def update_google_sheet(self, structured_result: list[dict[str, Any]]) -> None:
        """Update the Google Sheet with the structured result.

        Appends a new row by mapping structured_result keys to existing header columns.
        Columns not present in structured_result are left empty.
        Headers are cached per worksheet after the first fetch.
        """
        global GOOGLE_SHEET_HEADERS

        spreadsheet_id = self.config.google_sheets_spreadsheet_id
        worksheet_name = self.config.google_sheets_worksheet_name
        cache_key = f"{spreadsheet_id}:{worksheet_name}"

        @retry(
            retry=retry_if_exception(_is_retryable_google_error),
            wait=wait_exponential_jitter(initial=1, max=60),
            stop=stop_after_attempt(5),
            before_sleep=before_sleep_log(LOGGER, logging.INFO),
            reraise=True,
        )
        def _get_headers_with_retry():
            header_range = f"{worksheet_name}!1:1"
            header_response = (
                self.google_sheets_service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=header_range)
                .execute()
            )
            return header_response.get("values", [[]])[0]

        @retry(
            retry=retry_if_exception(_is_retryable_google_error),
            wait=wait_exponential_jitter(initial=1, max=60),
            stop=stop_after_attempt(5),
            before_sleep=before_sleep_log(LOGGER, logging.INFO),
            reraise=True,
        )
        def _append_rows_with_retry(rows):
            self.google_sheets_service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=f"{worksheet_name}!A1",
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body={"values": rows},
            ).execute()

        # Implement Google Sheet update logic using self.google_sheets_service
        if cache_key not in GOOGLE_SHEET_HEADERS:
            headers = _get_headers_with_retry()

            if not headers:
                raise ValueError(
                    f"No header row found in worksheet '{worksheet_name}'. "
                    "Cannot map structured_result keys to columns."
                )

            GOOGLE_SHEET_HEADERS[cache_key] = headers
            LOGGER.info(
                "Google Sheet headers cached cache_key=%s headers=%s",
                cache_key,
                headers,
            )

        if not structured_result:
            LOGGER.warning("structured_result is empty, skipping Google Sheet update.")
            return

        headers = GOOGLE_SHEET_HEADERS[cache_key]
        rows = [
            [str(item.get(col, "")) for col in headers] for item in structured_result
        ]

        _append_rows_with_retry(rows)

        LOGGER.info(
            "Google Sheet updated spreadsheet_id=%s worksheet=%s rows_written=%s",
            spreadsheet_id,
            worksheet_name,
            len(rows),
        )

    def validate_event(self, event: dict[str, Any]) -> bool:
        """Validate incoming SQS event payload.

        Returns True when the event contains one or more SQS records.
        Returns False for empty or malformed events without raising.
        """
        if event is None or not isinstance(event, dict):
            LOGGER.warning("Invalid event: event is None or not a dictionary")
            return False

        if "Records" not in event:
            LOGGER.warning("Invalid event: missing Records key")
            return False

        records = event.get("Records", [])
        if not isinstance(records, list):
            LOGGER.warning("Invalid event: Records is not a list")
            return False

        if not records:
            LOGGER.info("Empty Records list - nothing to process")
            return False

        return True

    def fetch_file_content(self, file_id: str, mime_type: str) -> bytes:
        """Fetch file content bytes from Google Drive for a given file.
        Uses MediaIoBaseDownload to handle streaming for large files.
        """
        LOGGER.info(
            f"Fetching file content for file_id: {file_id}, mime_type: {mime_type}"
        )

        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)

            done = False
            while done is False:
                status, done = downloader.next_chunk()
                if status:
                    LOGGER.debug("Download %d%%." % int(status.progress() * 100))

            return fh.getvalue()
        except Exception as exc:
            LOGGER.error(
                f"Failed to fetch file content from Google Drive for {file_id}: {str(exc)}"
            )
            raise

    def process_file(self, message: dict[str, Any]) -> dict[str, Any]:
        """Process a single file message."""
        document_type = self.determine_document_type(message)
        print(
            f"Determined document_type={document_type} for message_id={message.get('id')}"
        )

        # Fetch file content using the Drive file id and mimeType from message
        file_content = self.fetch_file_content(message["id"], message["mimeType"])
        print(
            f"Fetched file content for message_id={message.get('id')} content_length={len(file_content)}"
        )

        # Resolve the prompt for this document type
        prompt = self.get_prompt_for_document_type(document_type)
        print(
            f"Resolved prompt for document_type={document_type} prompt_length={len(prompt)}"
        )

        # Pick the document-type specific pre/post functions
        preprocess_function = self.get_preprocessing_function(document_type)
        print(
            f"Selected preprocess_function={preprocess_function.__name__} for document_type={document_type}"
        )
        postprocess_function = self.get_postprocessing_function(document_type)
        print(
            f"Selected postprocess_function={postprocess_function.__name__} for document_type={document_type}"
        )

        # Run preprocessing -> LLM -> postprocessing
        preprocessed_text = preprocess_function(file_content)
        print(
            f"Completed preprocessing for message_id={message.get('id')} preprocessed_length={len(preprocessed_text)}"
        )

        # quit lambda intentionally before llm call because llm quota exceeded
        return {
            "status": "llm_quota_exceeded",
            "document_type": document_type,
            "preprocess_function": preprocess_function,
            "postprocess_function": postprocess_function,
            "message_id": message.get("id"),
            "preprocessed_text": preprocessed_text,
        }
        llm_response = llm_call(
            prompt=prompt,
            text=preprocessed_text,
            model=self.config.llm_model,
            openai_api_key=self.config.openai_api_key,
            logger=LOGGER,
            json_response=True,
        )
        structured_result = postprocess_function(llm_response)

        # Update the results in a Google Sheet
        self.update_google_sheet(structured_result)

        # TODO: copy/move the source file to the configured processed
        # self.archive_file(message["id"])

        return {
            "status": "not_implemented",
            "document_type": document_type,
            "message_id": message.get("id"),
        }

    def archive_file(self, file_id: str) -> None:
        """Archive a processed file to the configured archive folder.

        Behavior is controlled by config.archive_move_file:
        - True:  move the file (copy to destination + remove from source)
        - False: copy the file (original stays, copy goes to archive)
        """
        archive_folder_id = self.config.archive_folder_id
        if not archive_folder_id:
            LOGGER.warning(
                "ARCHIVE_FOLDER_ID not configured, skipping archive for file_id=%s",
                file_id,
            )
            return

        try:
            if self.config.archive_move_file:
                # Fetch current parents before moving
                file_metadata = (
                    self.drive_service.files()
                    .get(fileId=file_id, fields="parents")
                    .execute()
                )
                current_parents = ",".join(file_metadata.get("parents", []))

                # Move: add new parent, remove all current parents
                self.drive_service.files().update(
                    fileId=file_id,
                    addParents=archive_folder_id,
                    removeParents=current_parents,
                    fields="id, parents",
                ).execute()

                LOGGER.info(
                    "Moved file file_id=%s to archive_folder_id=%s",
                    file_id,
                    archive_folder_id,
                )
            else:
                # Copy: original stays, new copy lands in archive folder
                self.drive_service.files().copy(
                    fileId=file_id,
                    body={"parents": [archive_folder_id]},
                    fields="id, parents",
                ).execute()

                LOGGER.info(
                    "Copied file file_id=%s to archive_folder_id=%s",
                    file_id,
                    archive_folder_id,
                )

        except HttpError as exc:
            LOGGER.error(
                "Failed to archive file file_id=%s move=%s error=%s",
                file_id,
                self.config.archive_move_file,
                str(exc),
            )
            raise

    def consume(self, event: dict[str, Any]) -> list[str]:
        """Iterate over SQS records and process them individually.
        Returns a list of message IDs that failed processing.
        """
        if self.check_kill_switch():
            LOGGER.warning(
                "KILL_SWITCH is enabled - failing invocation so SQS messages remain in queue"
            )
            # Re-throwing here because if the kill switch is on, we want the whole batch to remain in SQS.
            raise RuntimeError("kill_switch_enabled")

        if not self.validate_event(event):
            return []

        records = event.get("Records", [])
        failed_message_ids: list[str] = []

        for record in records:
            message_id = record.get("messageId")
            try:
                message_body = record.get("body")
                parsed_message = self.parse_message(message_body)
                LOGGER.info(
                    "Processing SQS message message_id=%s file_id=%s document_type=%s",
                    message_id,
                    parsed_message.get("id"),
                    parsed_message.get("document_type"),
                )
                self.process_file(parsed_message)
            except Exception as exc:
                LOGGER.error(
                    "Failed to process message message_id=%s error=%s",
                    message_id,
                    str(exc),
                    exc_info=True,
                )
                if message_id:
                    failed_message_ids.append(message_id)

        return failed_message_ids


def lambda_handler(event: dict, context: object) -> dict:
    """AWS Lambda handler entry point.
    Implements SQS partial batch failure reporting.
    """
    # Log the entire event to understand its structure
    LOGGER.info("Received event: %s", json.dumps(event))

    try:
        config = load_config()
        bootstrap_logging(config.log_level)
        LOGGER.info("Starting %s in %s", config.project_name, config.environment)

        consumer = ConsumerComponent(config)
        failed_ids = consumer.consume(event)

        return {"batchItemFailures": [{"itemIdentifier": mid} for mid in failed_ids]}
    except Exception as exc:
        # This catches errors during config loading or component initialization
        # If this fails, the entire batch will be retried by SQS
        LOGGER.exception("Critical consumer failure: %s", str(exc))
        raise
