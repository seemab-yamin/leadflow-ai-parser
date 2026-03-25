#!/usr/bin/env python3
"""
Smoke test: extract plain text from a PDF using Apache Tika (same code as the app).

Requires Java on PATH and ``tika`` from requirements.txt. Run from repo root:

    python scripts/test_tika_pdf.py /path/to/document.pdf
    python scripts/test_tika_pdf.py ./some.pdf --max-chars 500
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract text from a PDF via Tika (requires Java)."
    )
    parser.add_argument(
        "pdf",
        type=Path,
        help="Path to a PDF file",
    )
    parser.add_argument(
        "-n",
        "--max-chars",
        type=int,
        default=3000,
        metavar="N",
        help="Print at most this many characters of extracted text (0 = full text). Default: 3000",
    )
    args = parser.parse_args()

    from app.services.pdf_text.backends.tika import extract_text_with_tika

    pdf = args.pdf.resolve()
    print(f"File: {pdf}")
    if not pdf.is_file():
        print("Error: file does not exist.", file=sys.stderr)
        return 1

    try:
        text = extract_text_with_tika(str(pdf))
    except (FileNotFoundError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    n = len(text)
    print(f"Extracted length: {n} characters (after strip)")
    if n == 0:
        print("(No text — scanned PDF or empty document?)")
        return 0

    limit = args.max_chars
    preview = text if limit == 0 else text[:limit]
    print("--- text preview ---")
    print(preview)
    if limit > 0 and n > limit:
        print(f"--- ... truncated ({n - limit} more characters) ---")
    print("--- ok ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
