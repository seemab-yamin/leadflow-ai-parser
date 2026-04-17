from __future__ import annotations

import logging
import random
import time
from typing import Any

from googleapiclient.errors import HttpError

LOGGER = logging.getLogger(__name__)

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


def _list_with_retry(service, query: str, page_token: str | None, max_retries: int):
    retries_left = max_retries

    while True:
        try:
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
        except HttpError as e:
            if e.resp.status in [403, 429] and retries_left > 0:
                wait_time = (
                    min(
                        (2 ** (max_retries - retries_left)) + random.randint(0, 1000),
                        32000,
                    )
                    / 1000
                )
                time.sleep(wait_time)
                retries_left -= 1
                continue
            raise


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


def list_files(service, folder_id: str, max_retries: int = 5) -> list[dict[str, Any]]:
    """Fetch all files recursively under a folder using iterative traversal.

    Uses an explicit stack (DFS) to avoid recursion depth limits.
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
