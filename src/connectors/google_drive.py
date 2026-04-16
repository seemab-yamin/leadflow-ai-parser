from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from google.oauth2 import service_account
from googleapiclient.discovery import build


FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"


@dataclass(frozen=True)
class DriveItem:
    id: str
    name: str
    mime_type: str
    parent_id: str
    path: str

    @property
    def is_folder(self) -> bool:
        return self.mime_type == FOLDER_MIME_TYPE


def _build_drive_service(credentials_path: Path):
    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path),
        scopes=[DRIVE_READONLY_SCOPE],
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _list_children(service, folder_id: str) -> Iterator[dict]:
    page_token = None
    query = f"'{folder_id}' in parents and trashed = false"

    while True:
        response = (
            service.files()
            .list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType)",
                pageToken=page_token,
                pageSize=1000,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )

        for item in response.get("files", []):
            yield item

        page_token = response.get("nextPageToken")
        if not page_token:
            break


def list_drive_tree(credentials_path: Path, root_folder_id: str = "root") -> list[DriveItem]:
    service = _build_drive_service(credentials_path)

    items: list[DriveItem] = []
    stack: list[tuple[str, str]] = [(root_folder_id, "")]

    while stack:
        current_folder_id, current_path = stack.pop()

        for child in _list_children(service, current_folder_id):
            child_name = child["name"]
            child_path = f"{current_path}/{child_name}" if current_path else child_name

            drive_item = DriveItem(
                id=child["id"],
                name=child_name,
                mime_type=child["mimeType"],
                parent_id=current_folder_id,
                path=child_path,
            )
            items.append(drive_item)

            if drive_item.is_folder:
                stack.append((drive_item.id, child_path))

    return items
