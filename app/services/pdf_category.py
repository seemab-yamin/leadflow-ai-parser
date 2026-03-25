"""
Path helpers for **server cwd** batch runs (no staged upload).

Staged uploads use ``selection`` expansion in ``app.services.upload_jobs``; each PDF’s
category for parser routing is carried explicitly (see ``run_pdf_batch``’s
``pdf_category_by_path``). This module only supplies ``immediate_subfolder_category``
for legacy ``POST /api/process-batch`` calls that pass ``pdf_paths`` without
``upload_job_id`` (paths relative to the API process working directory).
"""

from __future__ import annotations

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
    ``ROOT_CATEGORY`` if the PDF sits directly under the selection.

    Used only for **non-staged** ``pdf_paths`` batch requests.
    """
    rp = (pdf_path or "").replace("\\", "/").strip()
    parts = [p for p in rp.split("/") if p]
    parts = _strip_picker_root_prefix(parts, picker_root_folder_name)
    if len(parts) <= 1:
        return ROOT_CATEGORY
    return parts[0]
