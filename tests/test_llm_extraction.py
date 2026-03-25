"""LLM extraction: logging and user-facing errors."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from app.services.llm_extraction import LLMExtractionError, extract_json_with_llm


def test_extract_json_with_llm_missing_prompt_logs_and_raises(caplog):
    with caplog.at_level("ERROR"):
        with pytest.raises(LLMExtractionError, match='could not process "DC/x.pdf"'):
            extract_json_with_llm(
                "body",
                llm_model="gpt-4o-mini",
                prompt_version="__nonexistent_prompt_version__",
                pdf_path="DC/x.pdf",
            )
    assert "LLM prompt missing or empty" in caplog.text
    assert "DC/x.pdf" in caplog.text


def test_extract_json_with_llm_invalid_json_logs_and_raises(caplog):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="{not json"))]
    mock_response.usage = MagicMock(prompt_tokens=1, completion_tokens=1)

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = mock_response

    openai_stub = ModuleType("openai")

    def _fake_openai(*_a, **_k):
        return fake_client

    openai_stub.OpenAI = _fake_openai
    sys.modules["openai"] = openai_stub
    try:
        with caplog.at_level("ERROR"):
            with pytest.raises(
                LLMExtractionError, match="could not read as structured JSON"
            ):
                extract_json_with_llm(
                    "body",
                    llm_model="gpt-4o-mini",
                    prompt_version="DC_Prob_Prompt_v7",
                    pdf_path="DC/case.pdf",
                )
    finally:
        del sys.modules["openai"]
    assert "LLM returned invalid JSON" in caplog.text
