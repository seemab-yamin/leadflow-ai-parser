from __future__ import annotations

import logging
import time

from tika import parser

from .base import PDFParser

LOGGER = logging.getLogger(__name__)


class TikaPDFParser(PDFParser):
    """PDF text extractor backed by tika-python.

    Accepts raw PDF bytes (for example from Google Drive `fh.getvalue()`) and
    returns extracted plain text.
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay_seconds: float = 1.0,
    ) -> None:
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def extract_text(self, content: bytes) -> str:
        if not content:
            raise ValueError("PDF content is empty")

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                LOGGER.info(
                    "Extracting PDF text with Tika (attempt %s/%s)",
                    attempt,
                    self.max_retries,
                )

                result = parser.from_buffer(
                    content,
                    headers={"Accept": "text/plain"},
                )

                extracted = (result or {}).get("content") or ""
                return extracted.strip()
            except Exception as exc:
                last_error = exc
                LOGGER.warning(
                    "Tika extraction attempt %s failed: %s", attempt, str(exc)
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds * attempt)

        raise RuntimeError(
            "Failed to extract text from PDF via Tika after retries"
        ) from last_error
