"""
Category-specific PDF → row parsers.

Parser dict keys are **implementation keys** (e.g. ``dc``); they must match
``app.core.supported_pdf_categories.PARSER_IMPLEMENTATION_KEYS``.

User-facing **category folder names** (e.g. ``DC``) map to those keys via
``app.core.supported_pdf_categories.resolve_parser_key_for_user_category_folder``.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.supported_pdf_categories import (
    PARSER_IMPLEMENTATION_KEYS,
    resolve_parser_key_for_user_category_folder,
)

from .dc import parse_dc_parser

PARSERS_BY_CATEGORY: dict[str, Callable[..., list[dict]]] = {
    "dc": parse_dc_parser,
}

if set(PARSERS_BY_CATEGORY.keys()) != set(PARSER_IMPLEMENTATION_KEYS):
    raise RuntimeError(
        "PARSERS_BY_CATEGORY keys must exactly match "
        "PARSER_IMPLEMENTATION_KEYS in app.core.supported_pdf_categories"
    )


def get_parser_for_category(category_folder_name: str) -> Callable[..., list[dict]] | None:
    """Resolve the user’s category folder name to a parser callable, if implemented."""
    impl_key = resolve_parser_key_for_user_category_folder(category_folder_name)
    if impl_key is None:
        return None
    return PARSERS_BY_CATEGORY.get(impl_key)
