"""Resolve PDF paths to absolute files for extraction."""

from __future__ import annotations

from pathlib import Path


def resolve_batch_pdf_path(
    pdf_path: str, *, source_root: str | None = None
) -> Path | None:
    """
    Return an absolute ``Path`` to the PDF if it exists on the server.

    Resolution order:
    1. If ``source_root`` is provided, join/sanitize against it.
    2. Otherwise, if ``pdf_path`` is already an absolute existing file, use it.
    """
    if not pdf_path or not str(pdf_path).strip():
        return None

    rel_norm = str(pdf_path).replace("\\", "/").strip()
    parts = [p for p in rel_norm.split("/") if p]
    if ".." in parts:
        return None

    if source_root:
        base = Path(source_root).expanduser().resolve()
        candidate = (base / Path(*parts)).resolve()
        if candidate == base or base in candidate.parents:
            if candidate.is_file():
                return candidate
        return None

    cand = Path(rel_norm).expanduser()
    if cand.is_file():
        return cand.resolve()

    return None
