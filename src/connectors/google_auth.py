from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import AppConfig

GOOGLE_CREDENTIALS: service_account.Credentials | None = None
GOOGLE_DRIVE_SERVICE: Any | None = None
GOOGLE_SHEETS_SERVICE: Any | None = None


def get_credentials(
    config: AppConfig, scopes: list[str]
) -> service_account.Credentials:
    """Build and cache Google service account credentials once per runtime."""
    global GOOGLE_CREDENTIALS

    if GOOGLE_CREDENTIALS is not None:
        return GOOGLE_CREDENTIALS

    GOOGLE_CREDENTIALS = service_account.Credentials.from_service_account_info(
        config.google_service_account_info,
        scopes=scopes,
    )
    return GOOGLE_CREDENTIALS


def get_google_sheets_service(credentials) -> Any:
    """Build and cache Google Sheets service client once per runtime."""
    global GOOGLE_SHEETS_SERVICE

    if GOOGLE_SHEETS_SERVICE is not None:
        return GOOGLE_SHEETS_SERVICE

    GOOGLE_SHEETS_SERVICE = build(
        "sheets",
        "v4",
        credentials=credentials,
        cache_discovery=False,
    )
    return GOOGLE_SHEETS_SERVICE


def get_google_drive_service(credentials) -> Any:
    """Build and cache Google Drive service client once per runtime."""
    global GOOGLE_DRIVE_SERVICE

    if GOOGLE_DRIVE_SERVICE is not None:
        return GOOGLE_DRIVE_SERVICE

    GOOGLE_DRIVE_SERVICE = build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )
    return GOOGLE_DRIVE_SERVICE
