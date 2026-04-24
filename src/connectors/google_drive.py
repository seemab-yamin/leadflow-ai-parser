from __future__ import annotations

import logging
from typing import Any

from googleapiclient.errors import HttpError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

LOGGER = logging.getLogger(__name__)

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


def _is_retryable_error(exception: Exception) -> bool:
    """Check if a Google API error is retryable (403 Rate Limit, 429, 5xx)."""
    if isinstance(exception, HttpError):
        # 403 can be rate limit (userRateLimitExceeded) or other errors.
        # 429 is always rate limit. 5xx is server error.
        return exception.resp.status in [403, 429] or exception.resp.status >= 500
    return False


def _list_with_retry(service, query: str, page_token: str | None, max_retries: int):

    @retry(
        retry=retry_if_exception(_is_retryable_error),
        wait=wait_exponential_jitter(initial=1, max=32),
        stop=stop_after_attempt(max_retries),
        before_sleep=before_sleep_log(LOGGER, logging.INFO),
        reraise=True,
    )
    def _execute():
        return (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType, size, modifiedTime, parents)",
                pageSize=500,
                pageToken=page_token,
            )
            .execute()
        )

    return _execute()


def list_directories(
    service, folder_id: str, max_retries: int = 5
) -> list[dict[str, Any]]:
    """List immediate child directories under a folder.

    These represent top-level document types under the configured root.
    """
    directories: list[dict[str, Any]] = []
    page_token = None
    query = (
        f"'{folder_id}' in parents and trashed=false and mimeType='{FOLDER_MIME_TYPE}'"
    )

    while True:
        results = _list_with_retry(service, query, page_token, max_retries)
        page_directories = results.get("files", [])
        directories.extend(page_directories)

        page_token = results.get("nextPageToken")
        LOGGER.info(
            "Fetched %d directories from folder=%s (nextPageToken=%s)",
            len(page_directories),
            folder_id,
            page_token,
        )

        if not page_token:
            break

    return directories


def list_files(
    service,
    folder_id: str,
    max_retries: int = 5,
    file_format: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch all files recursively under a folder using iterative traversal.

    Uses an explicit stack (DFS) to avoid recursion depth limits.

    When ``file_format`` is provided, only files matching that MIME type
    are returned (folders are still queried for traversal).
    """
    all_files: list[dict[str, Any]] = []
    stack: list[str] = [folder_id]
    visited_folders: set[str] = set()

    while stack:
        current_folder_id = stack.pop()

        # Circular reference protection / duplicate traversal protection
        if current_folder_id in visited_folders:
            continue
        visited_folders.add(current_folder_id)

        page_token = None
        while True:
            query = f"'{current_folder_id}' in parents and trashed=false"
            if file_format:
                query += (
                    f" and (mimeType='{FOLDER_MIME_TYPE}' "
                    f"or mimeType='{file_format}')"
                )
            results = _list_with_retry(service, query, page_token, max_retries)

            files = results.get("files", [])

            for item in files:
                if item.get("mimeType") == FOLDER_MIME_TYPE:
                    child_folder_id = item.get("id")
                    if child_folder_id and (child_folder_id not in visited_folders):
                        stack.append(child_folder_id)
                else:
                    all_files.append(item)

            page_token = results.get("nextPageToken")

            LOGGER.info(
                "Fetched %d items from Google Drive (folder: %s, page token: %s)",
                len(files),
                current_folder_id,
                page_token,
            )

            if not page_token:
                break

    return all_files
