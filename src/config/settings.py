from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import os


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class AppConfig:
    environment: str
    project_name: str
    raw_files_dir: Path
    google_credentials_path: Path | None
    google_service_account_secret_id: str | None
    google_drive_root_folder_id: str | None
    google_sheets_spreadsheet_id: str | None
    google_sheets_worksheet_name: str
    log_level: str


def _read_env(
    env: Mapping[str, str], key: str, default: str | None = None
) -> str | None:
    value = env.get(key)
    if value is None:
        return default
    stripped = value.strip()
    return stripped if stripped else default


def _read_path(
    env: Mapping[str, str], key: str, default: str | None = None
) -> Path | None:
    value = _read_env(env, key, default)
    return None if value is None else Path(value).expanduser()


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    source = os.environ if env is None else env

    environment = _read_env(source, "APP_ENV", "development") or "development"
    project_name = (
        _read_env(source, "PROJECT_NAME", "hb-raw-data-pipeline")
        or "hb-raw-data-pipeline"
    )
    raw_files_dir = Path(_read_env(source, "RAW_FILES_DIR", "raw") or "raw")
    google_credentials_path = _read_path(source, "GOOGLE_APPLICATION_CREDENTIALS")
    google_service_account_secret_id = _read_env(
        source, "GOOGLE_SERVICE_ACCOUNT_SECRET_ID"
    )
    google_drive_root_folder_id = _read_env(source, "GOOGLE_DRIVE_ROOT_FOLDER_ID")
    google_sheets_spreadsheet_id = _read_env(source, "GOOGLE_SHEETS_SPREADSHEET_ID")
    google_sheets_worksheet_name = (
        _read_env(source, "GOOGLE_SHEETS_WORKSHEET_NAME", "Sheet1") or "Sheet1"
    )
    log_level = _read_env(source, "LOG_LEVEL", "INFO") or "INFO"

    if google_credentials_path is None and google_service_account_secret_id is not None:
        from connectors.secrets_manager import materialize_secret_to_tmp

        google_credentials_path = materialize_secret_to_tmp(
            google_service_account_secret_id
        )

    if google_credentials_path is not None and not google_credentials_path.exists():
        raise ConfigError(
            f"Google credentials file not found: {google_credentials_path}"
        )

    if google_credentials_path is None:
        raise ConfigError(
            "Google credentials must be provided via GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_SERVICE_ACCOUNT_SECRET_ID"
        )

    return AppConfig(
        environment=environment,
        project_name=project_name,
        raw_files_dir=raw_files_dir,
        google_credentials_path=google_credentials_path,
        google_service_account_secret_id=google_service_account_secret_id,
        google_drive_root_folder_id=google_drive_root_folder_id,
        google_sheets_spreadsheet_id=google_sheets_spreadsheet_id,
        google_sheets_worksheet_name=google_sheets_worksheet_name,
        log_level=log_level,
    )
