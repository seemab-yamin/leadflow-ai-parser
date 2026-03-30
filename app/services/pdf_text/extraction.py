"""
PDF text extraction.

Register backends in ``_BACKENDS`` and select them via :func:`extract_text_from_pdf`.
"""

from __future__ import annotations

from collections.abc import Callable

from app.services.pdf_text.backends.docling import extract_text_with_docling
from app.services.pdf_text.backends.tika import extract_text_with_tika

_BACKENDS: dict[str, Callable[[str], str]] = {
    "tika": extract_text_with_tika,
    "docling": extract_text_with_docling,
}

DEFAULT_BACKEND = "tika"


def extract_text_from_pdf(
    pdf_path: str,
    *,
    backend: str | None = None,
) -> str:
    """
    Extract plain text from a PDF on disk.

    Parameters
    ----------
    pdf_path
        Absolute path to the PDF file (must exist).
    backend
        Registered backend name (default: ``\"tika\"`` — Apache Tika, requires Java).

    Returns
    -------
    str
        Stripped plain text (may be empty if the PDF has no extractable text).
    """
    if not pdf_path or not str(pdf_path).strip():
        return ""

    name = (backend or DEFAULT_BACKEND).strip().casefold()
    fn = _BACKENDS.get(name)
    if fn is None:
        raise ValueError(
            f"Unknown PDF text backend {backend!r}. "
            f"Choose one of: {', '.join(sorted(_BACKENDS))}."
        )
    return fn(pdf_path)
