"""
Extract text using Apache Tika (``tika`` Python package).

Requires a **JRE/JDK** on the server; the library may download the Tika JAR on first use.
"""

from __future__ import annotations

from typing import Any, Callable


def extract_text_with_tika(
    pdf_path: str,
    *,
    _from_file: Callable[[str], dict[str, Any] | None] | None = None,
) -> str:
    """
    Run Tika on a PDF file on disk and return stripped plain text.

    Parameters
    ----------
    pdf_path
        Absolute path to a readable ``.pdf`` file.

    Raises
    ------
    FileNotFoundError
        If ``pdf_path`` is not an existing file.
    RuntimeError
        If Tika/Java fails or returns an unexpected payload.
    """
    from pathlib import Path

    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    from_file = _from_file
    if from_file is None:
        try:
            from tika import parser as _tika_parser
        except ImportError as e:
            raise RuntimeError(
                "The 'tika' package is not installed. Add it to requirements and ensure Java is available."
            ) from e
        from_file = _tika_parser.from_file

    try:
        parsed = from_file(str(path.resolve()))
    except Exception as e:
        raise RuntimeError(
            f"Apache Tika failed to parse {path.name!r}. Is Java installed and on PATH? ({e})"
        ) from e

    if parsed is None:
        return ""

    content = parsed.get("content")
    if content is None:
        return ""

    if isinstance(content, bytes):
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            text = content.decode("latin-1", errors="replace")
    else:
        text = str(content)

    return text.strip()
