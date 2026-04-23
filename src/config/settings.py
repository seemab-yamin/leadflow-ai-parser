from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from connectors.parameters_manager import load_parameter_json


class ConfigError(ValueError):
    # TODO: Implement more specific exceptions for different config errors (e.g. MissingCredentialError, InvalidFolderError, etc.)
    pass


@dataclass(frozen=True)
class AppConfig:
    environment: str
    project_name: str
    raw_files_dir: Path
    google_service_account_info: dict[str, Any]
    google_service_account_parameter_id: str | None
    google_drive_folder_id: str | None
    google_sheets_spreadsheet_id: str | None
    google_sheets_worksheet_name: str
    log_level: str
    enabled_folders: list[str]
    kill_switch: bool
    sqs_queue_url: str | None
    sqs_batch_size: int
    prompts_dir: Path


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


def _read_bool(env: Mapping[str, str], key: str, default: bool = False) -> bool:
    value = _read_env(env, key)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes")


def _read_int(env: Mapping[str, str], key: str, default: int) -> int:
    value = _read_env(env, key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_json_list(
    env: Mapping[str, str], key: str, default: list[str] | None = None
) -> list[str]:
    value = _read_env(env, key)
    if value is None:
        return default or []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return default or []


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    source = os.environ if env is None else env

    environment = _read_env(source, "APP_ENV", "development") or "development"
    project_name = _read_env(source, "PROJECT_NAME", "")

    raw_files_dir = Path(_read_env(source, "RAW_FILES_DIR", "raw") or "raw")
    google_service_account_parameter_id = _read_env(
        source, "GOOGLE_SERVICE_ACCOUNT_PARAMETER_ID"
    )
    google_drive_folder_id = _read_env(source, "GOOGLE_DRIVE_FOLDER_ID")
    google_sheets_spreadsheet_id = _read_env(source, "GOOGLE_SHEETS_SPREADSHEET_ID")
    google_sheets_worksheet_name = (
        _read_env(source, "GOOGLE_SHEETS_WORKSHEET_NAME", "Sheet1") or "Sheet1"
    )
    log_level = _read_env(source, "LOG_LEVEL", "INFO") or "INFO"
    prompts_dir = Path(_read_env(source, "PROMPTS_DIR", "prompts") or "prompts")
    enabled_folders = _read_json_list(source, "ENABLED_FOLDERS", [])
    kill_switch = _read_bool(source, "KILL_SWITCH", False)
    sqs_queue_url = _read_env(source, "SQS_QUEUE_URL")
    sqs_batch_size = _read_int(source, "SQS_BATCH_SIZE", 10)

    if not google_drive_folder_id:
        raise ConfigError("GOOGLE_DRIVE_FOLDER_ID must be configured")

    if not google_service_account_parameter_id:
        raise ConfigError("GOOGLE_SERVICE_ACCOUNT_PARAMETER_ID must be configured")

    if not 1 <= sqs_batch_size <= 10:
        raise ConfigError("SQS_BATCH_SIZE must be between 1 and 10")

    google_service_account_info: dict[str, Any] | None = None
    if google_service_account_parameter_id is not None:
        google_service_account_info = load_parameter_json(
            google_service_account_parameter_id
        )

    if google_service_account_info is None:
        raise ConfigError(
            "Google credentials must be provided via GOOGLE_SERVICE_ACCOUNT_PARAMETER_ID"
        )

    return AppConfig(
        environment=environment,
        project_name=project_name,
        raw_files_dir=raw_files_dir,
        google_service_account_info=google_service_account_info,
        google_service_account_parameter_id=google_service_account_parameter_id,
        google_drive_folder_id=google_drive_folder_id,
        google_sheets_spreadsheet_id=google_sheets_spreadsheet_id,
        google_sheets_worksheet_name=google_sheets_worksheet_name,
        log_level=log_level,
        enabled_folders=enabled_folders,
        kill_switch=kill_switch,
        sqs_queue_url=sqs_queue_url,
        sqs_batch_size=sqs_batch_size,
        prompts_dir=prompts_dir,
    )
