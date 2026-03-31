"""
Extract text using Docling (:class:`docling.document_converter.DocumentConverter`).

Requires the `docling` package (see ``requirements.txt``).
"""

from __future__ import annotations

from pathlib import Path

from docling.document_converter import DocumentConverter


def extract_text_with_docling(pdf_path: str) -> str:
    """
    Run Docling on a PDF file on disk and return stripped plain text.

    Note: Docling returns markdown via `document.export_to_markdown()`. We return that
    markdown string as the "text" payload so downstream preprocessing can still
    normalize/clean it.
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    converter = DocumentConverter()
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
