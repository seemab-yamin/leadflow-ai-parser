"""Pluggable PDF → text extraction (multiple library backends later)."""

from .extraction import extract_text_from_pdf
from .paths import resolve_batch_pdf_path

__all__ = ["extract_text_from_pdf", "resolve_batch_pdf_path"]
