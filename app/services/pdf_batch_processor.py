"""
PDF batch processing — add your logic here.

Writes a single output file (for now a dummy .txt) so the API can later expose a download URL.
"""

from __future__ import annotations

import importlib
import time
from datetime import datetime, timezone
from pathlib import Path

# Generated batch outputs (gitignored). Resolved relative to repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_OUTPUT_DIR = _REPO_ROOT / "outputs" / "batch"


def batch_output_dir() -> Path:
    """Absolute directory where batch exports are written (created if missing)."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return _OUTPUT_DIR.resolve()


def resolve_batch_output_download(filename: str) -> Path:
    """
    Return the absolute path to a batch output file if ``filename`` is a safe basename
    under :func:`batch_output_dir`. Raises ``ValueError`` if the name is unsafe.
    """
    if not filename or filename != Path(filename).name:
        raise ValueError("not a single path segment")
    if "/" in filename or "\\" in filename or filename in (".", ".."):
        raise ValueError("invalid filename")
    root = batch_output_dir()
    target = (root / filename).resolve()
    if target != root and root not in target.parents:
        raise ValueError("outside batch output directory")
    if not target.is_file():
        raise FileNotFoundError(filename)
    return target


def _safe_output_stem(root_folder: str) -> str:
    return (
        "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in root_folder)[:80]
        or "batch"
    )


def _build_output_path(root_folder: str) -> Path:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    out_name = f"{_safe_output_stem(root_folder)}_{stamp}.xlsx"
    return _OUTPUT_DIR / out_name


def _parse_pdf(
    pdf_paths: list[str],
    *,
    picker_root_folder_name: str,
    source_root: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Parse each PDF path and return (successful_rows, failed_paths).

    Dispatches to category-specific parser parsers (see ``app.services.parsers``).
    """
    from app.services.parsers import get_parser_for_category
    from app.services.pdf_category import immediate_subfolder_category

    parser_rows: list[dict] = []
    failed_paths: list[dict] = []
    for pdf_path in pdf_paths:
        try:
            category = immediate_subfolder_category(pdf_path, picker_root_folder_name)
            parser_fn = get_parser_for_category(category)
            if parser_fn is None:
                failed_paths.append(
                    {
                        "pdf_path": pdf_path,
                        "error": f"No parser registered for category {category!r}.",
                    }
                )
                continue
            parsed = parser_fn(pdf_path, source_root=source_root)
            if isinstance(parsed, list):
                parser_rows.extend(parsed)
            else:
                failed_paths.append(
                    {
                        "pdf_path": pdf_path,
                        "error": "Parser returned non-list payload.",
                    }
                )
        except Exception as exc:
            failed_paths.append({"pdf_path": pdf_path, "error": str(exc)})
        # Throttle parsing throughput a bit for now.
        time.sleep(0.1)
    return parser_rows, failed_paths


def _write_excel_output(
    *,
    out_path: Path,
    parser_rows: list[dict],
    failed_paths: list[dict],
) -> None:
    """
    Write an Excel workbook directly from parser rows.

    Sheets:
    - ParsedRows: direct parser output rows
    - FailedPaths: parser failures (if any)
    """
    # Lazy import keeps module import cheap and avoids hard dependency at import time.
    pd = importlib.import_module("pandas")
    if parser_rows:
        parsed_df = pd.DataFrame(parser_rows)
    else:
        parsed_df = pd.DataFrame([{"info": "No parser rows returned."}])

    failed_df = pd.DataFrame(failed_paths, columns=["pdf_path", "error"])

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        parsed_df.to_excel(writer, sheet_name="ParsedRows", index=False)
        if not failed_df.empty:
            failed_df.to_excel(writer, sheet_name="FailedPaths", index=False)


def run_pdf_batch(
    *,
    root_folder: str,
    pdf_paths: list[str] | None = None,
    source_root: str | None = None,
) -> tuple[str, list[dict], int]:
    """
    Process the PDF batch and write **one** Excel output file.

    Returns
    -------
    (output_path, failed_paths, pdf_paths_attempted)
        Absolute path to the ``.xlsx`` file, per-file failure rows
        (``pdf_path``, ``error``), and how many PDF paths were attempted
        (for transparent UI summaries).
    """
    paths = list(pdf_paths or [])
    out_path = _build_output_path(root_folder)

    parser_rows, failed_paths = _parse_pdf(
        paths, picker_root_folder_name=root_folder, source_root=source_root
    )
    _write_excel_output(
        out_path=out_path,
        parser_rows=parser_rows,
        failed_paths=failed_paths,
    )
    return str(out_path.resolve()), failed_paths, len(paths)
