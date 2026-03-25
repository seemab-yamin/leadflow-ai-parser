#!/usr/bin/env python3
"""
Smoke test: verify the configured AI service (OpenAI) is reachable.

Run from repo root:

    python scripts/test_ai_service.py
    python scripts/test_ai_service.py --model gpt-5.1-2025-11-13

Exit codes:
  - 0: service responded and we parsed a JSON response
  - 1: request failed or response could not be parsed
  - 2: missing configuration (e.g. OPENAI_API_KEY / model)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def _get_default_model() -> str | None:
    try:
        from app.core.config import settings

        return settings.llm_model
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Check whether the AI service is alive.")
    parser.add_argument(
        "--model",
        default=_get_default_model(),
        help="OpenAI model id. Defaults to config.json dc llm_model.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Request timeout seconds (best-effort; depends on OpenAI client).",
    )
    args = parser.parse_args()

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("openai_api_key")
    if not api_key:
        print("Error: missing OPENAI_API_KEY in environment.", file=sys.stderr)
        return 2
    if not args.model:
        print("Error: missing --model and config.json dc llm_model.", file=sys.stderr)
        return 2

    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "Return ONLY a valid JSON object with keys: ok (boolean) and "
                "service (string). Do not include markdown."
            ),
        },
        {"role": "user", "content": "ping"},
    ]

    try:
        try:
            response = client.chat.completions.create(
                model=args.model,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
                reasoning_effort="none",
                verbosity="low",
                # best-effort: newer openai libs may respect client-level timeouts
            )
        except TypeError:
            # Some models / client versions may not accept reasoning_effort/verbosity.
            response = client.chat.completions.create(
                model=args.model,
                temperature=0,
                messages=messages,
                response_format={"type": "json_object"},
            )

        content = response.choices[0].message.content
        if not isinstance(content, str):
            raise ValueError("AI response content was not a string.")
        parsed = json.loads(content)
        ok = parsed.get("ok", None)
        service = parsed.get("service", None)

        print("AI service OK")
        print("model:", args.model)
        print("service:", service)
        print("ok:", ok)
        return 0
    except Exception as e:
        print("AI service FAILED:", str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

