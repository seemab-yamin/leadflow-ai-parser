from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path


def init_docling():

    # from huggingface_hub import constants

    # constants.HF_HUB_CACHE = ".cache/huggingface/hub"
    # print(f"DEBUG: HF_HUB_CACHE={constants.HF_HUB_CACHE}")

    import os

    print(f"DEBUG: DOCLING_ARTIFACTS_PATH={os.getenv('DOCLING_ARTIFACTS_PATH')}")

    from docling.document_converter import DocumentConverter

    return DocumentConverter()


_CONVERTER = None


def _get_converter():
    """Lazily initialize the Docling converter."""
    global _CONVERTER
    if _CONVERTER is None:
        _CONVERTER = init_docling()
    return _CONVERTER


from .base import PDFParser

LOGGER = logging.getLogger(__name__)


class DoclingPDFParser(PDFParser):
    """PDF text extractor backed by docling.

    Accepts raw PDF bytes (for example from Google Drive `fh.getvalue()`) and
    returns extracted plain text as markdown.
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

        converter = _get_converter()

        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                LOGGER.info(
                    "Extracting PDF text with Docling (attempt %s/%s)",
                    attempt,
                    self.max_retries,
                )

                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
                    tmp.write(content)
                    tmp.flush()
                    tmp_path = Path(tmp.name)

                    result = converter.convert(str(tmp_path.resolve()))

                doc = getattr(result, "document", None)
                if doc is None:
                    LOGGER.warning("Docling returned no document object")
                    return ""

                export_fn = getattr(doc, "export_to_markdown", None)
                if not callable(export_fn):
                    LOGGER.warning("Docling document has no export_to_markdown method")
                    return ""

                return str(export_fn()).strip()

            except Exception as exc:
                last_error = exc
                LOGGER.warning(
                    "Docling extraction attempt %s failed: %s", attempt, str(exc)
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay_seconds * attempt)

        raise RuntimeError(
            "Failed to extract text from PDF via Docling after retries"
        ) from last_error
