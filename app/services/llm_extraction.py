from __future__ import annotations

import json
from pathlib import Path

from app.core.config import settings
from app.core.logging_setup import get_logger

logger = get_logger()


class LLMExtractionError(RuntimeError):
    """Raised when structured JSON could not be obtained from the LLM (user-facing message in args)."""

    def __init__(self, message: str, *, pdf_path: str | None = None) -> None:
        self.pdf_path = pdf_path
        super().__init__(message)


def _file_phrase(pdf_path: str | None) -> str:
    if pdf_path:
        return f'We could not process "{pdf_path}". '
    return "We could not complete AI extraction for this document. "


def _load_prompt_text(prompt_version: str) -> str:
    """Load a versioned prompt text file from prompts/<version>.txt."""
    prompt_path = (
        Path(__file__).resolve().parents[2] / "prompts" / f"{prompt_version}.txt"
    )
    if not prompt_path.is_file():
        return ""
    try:
        prompt = prompt_path.read_text(encoding="utf-8").strip()
    except Exception:
        logger.exception(
            "Failed to read LLM prompt file prompt_version=%s path=%s",
            prompt_version,
            prompt_path,
        )
        return ""
    return prompt


def extract_json_with_llm(
    text: str,
    *,
    llm_model: str,
    prompt_version: str,
    pdf_path: str | None = None,
) -> dict:
    """
    Sync LLM JSON extraction. Returns a dict on success.

    Raises
    ------
    LLMExtractionError
        User-facing message; callers (e.g. batch) can surface this next to ``pdf_path``.
    """
    prompt = _load_prompt_text(prompt_version)
    if not prompt:
        logger.error(
            "LLM prompt missing or empty prompt_version=%s pdf_path=%s",
            prompt_version,
            pdf_path,
        )
        raise LLMExtractionError(
            _file_phrase(pdf_path)
            + f"The extraction instructions file is missing or empty (prompt version {prompt_version!r}).",
            pdf_path=pdf_path,
        )
    file_phrase = _file_phrase(pdf_path)
    try:
        from openai import OpenAI  # type: ignore[reportMissingImports]

        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=llm_model,
            temperature=0,
            response_format={"type": "json_object"},
            reasoning_effort="none",
            verbosity="low",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "### TEXT DATA ###\n" + text},
            ],
        )
        usage = response.usage
        output_text = response.choices[0].message.content
        if output_text is None or not str(output_text).strip():
            logger.error(
                "LLM returned empty content model=%s pdf_path=%s",
                llm_model,
                pdf_path,
            )
            raise LLMExtractionError(
                file_phrase + "The AI returned an empty response. Please try again.",
                pdf_path=pdf_path,
            )
        parsed = json.loads(output_text)
        if usage is not None:
            logger.info(
                "LLM extraction succeeded pdf_path=%s model=%s prompt_version=%s "
                "prompt_tokens=%s completion_tokens=%s",
                pdf_path,
                llm_model,
                prompt_version,
                usage.prompt_tokens,
                usage.completion_tokens,
            )
        else:
            logger.info(
                "LLM extraction succeeded pdf_path=%s model=%s prompt_version=%s usage=unavailable",
                pdf_path,
                llm_model,
                prompt_version,
            )
        return parsed
    except LLMExtractionError:
        raise
    except json.JSONDecodeError as e:
        logger.exception(
            "LLM returned invalid JSON model=%s prompt_version=%s pdf_path=%s",
            llm_model,
            prompt_version,
            pdf_path,
        )
        raise LLMExtractionError(
            file_phrase
            + "The AI returned data we could not read as structured JSON. Please try again.",
            pdf_path=pdf_path,
        ) from e
    except Exception as e:
        logger.exception(
            "LLM extraction failed model=%s prompt_version=%s pdf_path=%s",
            llm_model,
            prompt_version,
            pdf_path,
        )
        raise LLMExtractionError(
            file_phrase
            + "The AI service failed or could not be reached. Please try again in a moment.",
            pdf_path=pdf_path,
        ) from e
