"""
Category-specific PDF → row parsers.

Keys must match :data:`app.core.supported_pdf_categories.SUPPORTED_BATCH_FOLDER_CATEGORIES`.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.supported_pdf_categories import SUPPORTED_BATCH_FOLDER_CATEGORIES

from .dc import parse_dc_parser

# Normalized category key → parser (must stay in sync with ``supported_pdf_categories``).
PARSERS_BY_CATEGORY: dict[str, Callable[..., list[dict]]] = {
    "dc": parse_dc_parser,
}

if set(PARSERS_BY_CATEGORY.keys()) != set(SUPPORTED_BATCH_FOLDER_CATEGORIES):
    raise RuntimeError(
        "PARSERS_BY_CATEGORY keys must exactly match "
        "SUPPORTED_BATCH_FOLDER_CATEGORIES in app.core.supported_pdf_categories"
    )


def get_parser_for_category(category_name: str) -> Callable[..., list[dict]] | None:
    """Return the parser for a folder category, or ``None`` if not implemented."""
    key = category_name.strip().casefold()
    return PARSERS_BY_CATEGORY.get(key)
