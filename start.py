#!/usr/bin/env python3
"""
Start the LeadfFlow AI Parser (FastAPI) with uvicorn.

From the repository root::

    python run.py
    python run.py --host 0.0.0.0 --port 8000
    python run.py --reload

Packaging (PyInstaller, etc.): point the build entry point at this file. When
``sys.frozen`` is set, the process ``chdir``s to the executable’s directory so
``outputs/`` and ``logs-dir/`` are created beside the binary. The non-reload
path passes the ASGI ``app`` object into ``uvicorn.Server`` (no string import),
which matches a reliable PyInstaller layout. You still need to ship ``app/``,
templates, static assets, ``prompts/``, and ``config.json`` (or set paths via
env) as required by your bundle layout.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _is_port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _find_free_port(host: str, start_port: int, max_attempts: int = 20) -> int:
    for port in range(start_port, start_port + max_attempts):
        if _is_port_available(host, port):
            return port
    raise RuntimeError(
        f"No free port between {start_port} and {start_port + max_attempts - 1}."
    )


def _resolve_listen_port(host: str, preferred: int, *, auto_find: bool) -> int:
    if _is_port_available(host, preferred):
        return preferred
    if not auto_find:
        print(
            f"\nERROR: Port {preferred} is already in use on {host!r}. "
            "Free the port or pass --port.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    found = _find_free_port(host, preferred + 1)
    print(f"Port {preferred} in use; using {found} instead.", file=sys.stderr)
    return found


def _browser_host(host: str) -> str:
    if host in ("0.0.0.0", "::", ""):
        return "127.0.0.1"
    if host == "::1":
        return "[::1]"
    return host


def _wait_then_open_browser(host: str, port: int) -> None:
    url = f"http://{_browser_host(host)}:{port}/"
    for attempt in range(40):
        try:
            urlopen(url, timeout=1)
            break
        except (URLError, OSError, TimeoutError):
            time.sleep(0.25)
    else:
        print(f"Warning: server did not respond at {url}; opening browser anyway.")
    print(f"Opening browser at {url}")
    webbrowser.open(url)


def _start_browser_thread(host: str, port: int) -> None:
    thread = threading.Thread(
        target=_wait_then_open_browser,
        args=(host, port),
        daemon=True,
    )
    thread.start()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run LeadfFlow AI Parser (uvicorn + app.main).",
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
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open a browser tab (default: open when running as a frozen exe)",
    )
    args = parser.parse_args()

    root = _project_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    if getattr(sys, "frozen", False):
        os.chdir(root)

    import uvicorn

    # Import ASGI app for PyInstaller (static analysis + direct reference for Server).
    from app.main import app as asgi_app  # noqa: E402

    use_reload = bool(args.reload) and not getattr(sys, "frozen", False)
    log_level = (os.environ.get("UVICORN_LOG_LEVEL") or "info").lower()

    if use_reload:
        # Reloader expects an import string so it can respawn workers.
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            reload=True,
            log_level=log_level,
        )
        return 0

    frozen = getattr(sys, "frozen", False)
    listen_port = args.port
    if frozen:
        listen_port = _resolve_listen_port(
            args.host,
            args.port,
            auto_find=True,
        )

    open_browser = frozen and not args.no_browser
    if open_browser:
        _start_browser_thread(args.host, listen_port)

    config = uvicorn.Config(
        app=asgi_app,
        host=args.host,
        port=listen_port,
        log_level=log_level,
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
