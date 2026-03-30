"""
Extract text using Docling (:class:`docling.document_converter.DocumentConverter`).

This backend is optional at runtime. If `docling` is not installed, extracting with
`backend="docling"` raises a clear `RuntimeError`.
"""

from __future__ import annotations

from typing import Any, Callable


def extract_text_with_docling(
    pdf_path: str,
    *,
    _DocumentConverter: Callable[[], Any] | None = None,
) -> str:
    """
    Run Docling on a PDF file on disk and return stripped plain text.

    Note: Docling returns markdown via `document.export_to_markdown()`. We return that
    markdown string as the "text" payload so downstream preprocessing can still
    normalize/clean it.
    """
    from pathlib import Path

    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if _DocumentConverter is None:
        try:
            # Avoid static imports so local type-checkers/editors don't error when
            # `docling` isn't installed.
            import importlib

            _mod = importlib.import_module("docling.document_converter")
            _DC = getattr(_mod, "DocumentConverter")
        except ImportError as e:
            raise RuntimeError(
                "The 'docling' package is not installed. Install it to use backend='docling'."
            ) from e
        _DocumentConverter = _DC

    converter = _DocumentConverter()
    # Match the user's snippet: convert -> result.document.export_to_markdown()
    result = converter.convert(str(path.resolve()))
    doc = getattr(result, "document", None)
    if doc is None:
        return ""

    export_fn = getattr(doc, "export_to_markdown", None)
    if not callable(export_fn):
        return ""

    try:
        md = export_fn()
    except Exception:
        return ""

    return str(md).strip()
