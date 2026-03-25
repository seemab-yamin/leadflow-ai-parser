#!/usr/bin/env python3
"""
Start the LeadfFlow AI Parser (FastAPI) with uvicorn.

From the repository root::

    python run.py
    python run.py --host 0.0.0.0 --port 8000
    python run.py --reload

Packaging (PyInstaller, etc.): point the build entry point at this file. When
``sys.frozen`` is set, the process ``chdir``s to the executable’s directory so
``outputs/`` and ``logs-dir/`` are created beside the binary. You still need to
ship ``app/``, templates, static assets, ``prompts/``, and ``config.json`` (or
set paths via env) as required by your bundle layout.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run LeadfFlow AI Parser (uvicorn + app.main:app).",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind address (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Auto-reload on code changes (development only; ignored when frozen)",
    )
    args = parser.parse_args()

    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    if getattr(sys, "frozen", False):
        os.chdir(root)

    import uvicorn

    use_reload = bool(args.reload) and not getattr(sys, "frozen", False)
    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=use_reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
