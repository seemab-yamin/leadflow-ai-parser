import json
import logging

import openai
from openai import OpenAI
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class LLMExtractionError(RuntimeError):
    """Raised when structured JSON could not be obtained from the LLM (user-facing message in args)."""

    def __init__(self, message: str, *, pdf_path: str | None = None) -> None:
        self.pdf_path = pdf_path
        super().__init__(message)


_openai_client: OpenAI | None = None


def _get_openai_client(api_key: str) -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def llm_call(
    prompt: str,
    text: str,
    model: str,
    openai_api_key: str,
    logger: logging.Logger,
    json_response: bool = False,
) -> dict:
    """Unified LLM abstraction.

    Inputs: prompt + text + model
    Output: structured response dictionary

    Args:
        prompt: System prompt string.
        text: User content to process.
        model: LLM model identifier.
        json_response: If True, instructs the model to return valid JSON
                    and parses the response before returning.
    """

    client = _get_openai_client(openai_api_key)

    request_params = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "### TEXT DATA ###\n" + text},
        ],
    }

    if json_response:
        request_params["response_format"] = {"type": "json_object"}

    try:
        retr = Retrying(
            retry=retry_if_exception_type(openai.RateLimitError),
            wait=wait_exponential(multiplier=2, min=1, max=60),
            stop=stop_after_attempt(5),
            before_sleep=before_sleep_log(logger, logging.INFO),
            reraise=True,
        )
        response = retr(client.chat.completions.create, **request_params)
    except openai.RateLimitError as e:
        raise LLMExtractionError(
            "The AI service is currently overloaded. Please try again in a few minutes."
        ) from e
    except (
        openai.AuthenticationError,
        openai.BadRequestError,
        openai.NotFoundError,
    ) as e:
        logger.error("LLM non-retryable error model=%s error=%s", model, str(e))
        raise LLMExtractionError(
            "A configuration or request error occurred with the AI service. Contact support."
        ) from e
    except Exception as e:
        logger.exception("LLM call failed model=%s", model)
        raise LLMExtractionError(
            "The AI service failed or could not be reached. Please try again in a moment."
        ) from e

    output_text = response.choices[0].message.content
    usage = response.usage

    if not output_text or not output_text.strip():
        logger.error("LLM returned empty content model=%s", model)
        raise LLMExtractionError("The AI returned an empty response. Please try again.")

    if usage is not None:
        logger.info(
            "LLM call succeeded model=%s prompt_tokens=%s completion_tokens=%s",
            model,
            usage.prompt_tokens,
            usage.completion_tokens,
        )

    if json_response:
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as e:
            logger.exception("LLM returned invalid JSON model=%s", model)
            raise LLMExtractionError(
                "The AI returned data we could not read as structured JSON. Please try again."
            ) from e
        return parsed

    return {"content": output_text}
