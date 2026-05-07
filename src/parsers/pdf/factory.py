from __future__ import annotations

from .base import PDFParser
from .docling_parser import DoclingPDFParser
from .tika_parser import TikaPDFParser


def get_pdf_parser(method: str = "tika") -> PDFParser:
    """Return a PDF parser implementation by method name.

    Currently supported:
    - tika (default)
    """
    normalized = (method or "tika").strip().lower()

    if normalized == "tika":
        return TikaPDFParser()
    if normalized == "docling":
        return DoclingPDFParser()

    raise ValueError(f"Unsupported PDF parser method: {method}")
