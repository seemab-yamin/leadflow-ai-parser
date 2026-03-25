import json
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH), env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "dev"
    log_dir: str = "logs-dir"
    # If not set, derive from APP_ENV/app_env:
    # - dev -> DEBUG
    # - otherwise -> INFO
    log_level: str | None = None
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5
    openai_api_key: str | None = None
    _llm_model: str | None = None
    _dc_prompt_version: str | None = None
    # Minimum characters in preprocessed Tika text before calling the LLM (DC parser).
    _dc_min_preprocessed_chars: int = 80

    @property
    def llm_model(self) -> str:
        if not self._llm_model:
            raise RuntimeError("Missing 'llm_model' in config.json")
        return self._llm_model

    @property
    def dc_prompt_version(self) -> str:
        if not self._dc_prompt_version:
            raise RuntimeError("Missing 'dc_prompt_version' in config.json")
        return self._dc_prompt_version

    @property
    def dc_min_preprocessed_chars(self) -> int:
        return self._dc_min_preprocessed_chars

    def model_post_init(self, __context) -> None:  # type: ignore[override]
        cfg_path = _REPO_ROOT / "config.json"
        if not cfg_path.is_file():
            return
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return
        model = str(data.get("llm_model") or "").strip()
        if model:
            object.__setattr__(self, "_llm_model", model)
        version = str(
            data.get("dc_prompt_version") or data.get("dc_llm_version") or ""
        ).strip()
        if version:
            object.__setattr__(self, "_dc_prompt_version", version)
        raw_min = data.get("dc_min_preprocessed_chars")
        if raw_min is not None:
            try:
                n = int(raw_min)
                if n >= 1:
                    object.__setattr__(self, "_dc_min_preprocessed_chars", n)
            except (TypeError, ValueError):
                pass


settings = Settings()
