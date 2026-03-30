"""
Source of truth: **parser implementations** available in code (internal keys, e.g. ``dc``).

Document **categories** (folder names like ``DC``, ``VA Alexandria``) are defined only
by the user’s directory layout and by what they select in the UI — not by a fixed
frozenset of “allowed folder names” for inference.

- Parser keys live in ``PARSER_IMPLEMENTATION_KEYS``.
- Register callables in ``app.services.parsers.PARSERS_BY_CATEGORY`` (same keys).
- Map a **user category folder name** → parser key via
  ``resolve_parser_key_for_user_category_folder`` (convention / config until expanded).

See ``app.core.batch_selection_contract`` for the end-to-end selection workflow.
"""

from __future__ import annotations

# Keys used in ``PARSERS_BY_CATEGORY`` (lowercase, stable).
PARSER_IMPLEMENTATION_KEYS: frozenset[str] = frozenset(
    {
        "dc",
        "va_alexandria",
    }
)

# Human-readable labels for parser keys (errors, logs, docs).
DISPLAY_NAME_BY_PARSER_KEY: dict[str, str] = {
    "dc": "DC",
    "va_alexandria": "VA Alexandria",
}

if set(DISPLAY_NAME_BY_PARSER_KEY.keys()) != set(PARSER_IMPLEMENTATION_KEYS):
    raise RuntimeError(
        "DISPLAY_NAME_BY_PARSER_KEY keys must exactly match PARSER_IMPLEMENTATION_KEYS"
    )

# Backward compatibility: old name referred to the same set of parser keys.
SUPPORTED_BATCH_FOLDER_CATEGORIES: frozenset[str] = PARSER_IMPLEMENTATION_KEYS
DISPLAY_NAME_BY_NORMALIZED_KEY: dict[str, str] = DISPLAY_NAME_BY_PARSER_KEY


def resolve_parser_key_for_user_category_folder(
    category_folder_name: str,
) -> str | None:
    """
    Map the **user’s category folder label** (from ``selection`` or legacy path layout)
    to a parser implementation key.

    Conventions today: ``DC`` / ``dc`` → ``dc``. Add entries here (and in
    ``PARSERS_BY_CATEGORY``) when new jurisdiction parsers ship, e.g. a dedicated
    ``va_alexandria`` key once implemented.
    """
    key = category_folder_name.strip().casefold()
    if key == "dc":
        return "dc"
    if key == "va alexandria":
        return "va_alexandria"
    return None


def is_supported_batch_folder_category(category_name: str) -> bool:
    """Whether this category folder name maps to an implemented parser."""
    return resolve_parser_key_for_user_category_folder(category_name) is not None


def supported_category_display_names() -> tuple[str, ...]:
    """Sorted labels for parsers that exist in code (e.g. ``(\"DC\",)``)."""
    keys = sorted(PARSER_IMPLEMENTATION_KEYS)
    return tuple(DISPLAY_NAME_BY_PARSER_KEY[k] for k in keys)


def describe_supported_categories_for_user() -> str:
    """Short sentence listing implemented parsers (not folder names)."""
    labels = supported_category_display_names()
    if not labels:
        return "No parsers are implemented for batch processing yet."
    if len(labels) == 1:
        return f'Only the "{labels[0]}" parser pipeline is implemented right now'
    joined = ", ".join(f'"{label}"' for label in labels)
    return f"Only these parser pipelines are implemented right now: {joined}"


def batch_no_implemented_parser_message(categories_in_batch: list[str]) -> str:
    """
    HTTP 400 body when every path in the batch resolves to a category with no parser.

    ``categories_in_batch`` should list distinct user-facing category names (e.g. ``VA Alexandria``).
    """
    impl = supported_category_display_names()
    impl_txt = ", ".join(f'"{x}"' for x in impl) if impl else "(none yet)"
    uniq = sorted({c.strip() for c in categories_in_batch if c and str(c).strip()})
    if not uniq:
        missing_txt = "(could not determine categories)"
    else:
        missing_txt = ", ".join(f'"{x}"' for x in uniq)
    return (
        "None of the PDFs in this batch use a parser that is implemented yet. "
        f"Categories in this batch without a parser: {missing_txt}. "
        f"Implemented today: {impl_txt}."
    )


def process_batch_unsupported_categories_message() -> str:
    """Generic message when batch categories cannot be matched to parsers (no path list)."""
    return (
        describe_supported_categories_for_user()
        + " Adjust your folder selection so at least one PDF is under a category "
        "that has a parser, or add a parser mapping for your category names."
    )
