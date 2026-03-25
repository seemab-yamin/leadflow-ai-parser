"""
Classify PDFs by the immediate subfolder under the user-selected root.

Each top-level folder under the picked directory is treated as a category (e.g. ``DC``).
PDFs placed directly in the root of the selection use :data:`ROOT_CATEGORY`.

Browser folder pickers usually prefix ``webkitRelativePath`` with the selected folder name
(e.g. ``MyPick/DC/file.pdf``). Pass ``picker_root_folder_name`` so that segment is stripped
and categories reflect **child** folders (``DC``), not the pick root.
"""

from __future__ import annotations

from typing import Iterable

from app.core.supported_pdf_categories import is_supported_batch_folder_category

# Sentinel category for PDFs whose relative path has no subfolder segment (e.g. "doc.pdf").
ROOT_CATEGORY = "(root)"


def _strip_picker_root_prefix(
    parts: list[str], picker_root_folder_name: str | None
) -> list[str]:
    """
    Browsers include the selected directory name as the first segment in
    ``webkitRelativePath`` (e.g. ``MyFolder/DC/doc.pdf``). Strip it when it matches
    the client-provided root folder name so categories are **child** folders.
    """
    if not parts or not picker_root_folder_name:
        return parts
    root = picker_root_folder_name.strip()
    if not root:
        return parts
    if parts[0].casefold() == root.casefold():
        return parts[1:]
    return parts


def immediate_subfolder_category(
    pdf_path: str, picker_root_folder_name: str | None = None
) -> str:
    """
    Return the first path segment under the picked root (child folder), or
    :data:`ROOT_CATEGORY` if the PDF sits directly under the selection.

    ``picker_root_folder_name`` should be the folder name from the browser picker
    (same as ``root_folder_name`` / ``root_folder`` in the API); omit for filesystem
    paths that are already relative to the root without that extra prefix.
    """
    rp = (pdf_path or "").replace("\\", "/").strip()
    parts = [p for p in rp.split("/") if p]
    parts = _strip_picker_root_prefix(parts, picker_root_folder_name)
    if len(parts) <= 1:
        return ROOT_CATEGORY
    return parts[0]


def is_parser_supported_category(category_name: str) -> bool:
    """
    ``True`` when batch parsing is implemented for this category.

    Defined in :mod:`app.core.supported_pdf_categories` (single source of truth).
    """
    return is_supported_batch_folder_category(category_name)


def sort_categories_for_display(names: Iterable[str]) -> list[str]:
    """Supported categories first, then alphabetical; :data:`ROOT_CATEGORY` last."""

    def sort_key(name: str) -> tuple[int, int, str]:
        root = name == ROOT_CATEGORY
        supported = is_parser_supported_category(name)
        return (0 if supported else 1, 1 if root else 0, name.casefold())

    return sorted(names, key=sort_key)


def filter_supported_pdf_paths(
    paths: list[str] | None, picker_root_folder_name: str | None = None
) -> list[str]:
    """Keep only paths whose immediate subfolder category is parser-supported."""
    if not paths:
        return []
    return [
        p
        for p in paths
        if is_parser_supported_category(
            immediate_subfolder_category(p, picker_root_folder_name)
        )
    ]
