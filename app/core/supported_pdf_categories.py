"""
Source of truth: which **immediate subfolder** names (batch folder categories) the app
can process today.

- Add a normalized key (lowercase) to :data:`SUPPORTED_BATCH_FOLDER_CATEGORIES`.
- Add a matching display label in :data:`DISPLAY_NAME_BY_NORMALIZED_KEY` for user-facing copy.
- Register a parser for that key in ``app.services.parsers.PARSERS_BY_CATEGORY``.

Anything not listed here can appear in the UI folder summary but is not processed by process-batch.
"""

from __future__ import annotations

# Keys are compared with :func:`str.casefold` on the folder segment (e.g. ``DC`` → ``dc``).
SUPPORTED_BATCH_FOLDER_CATEGORIES: frozenset[str] = frozenset(
    {
        "dc",
    }
)

# Stable display strings for errors, logs, and UI copy (key → label).
DISPLAY_NAME_BY_NORMALIZED_KEY: dict[str, str] = {
    "dc": "DC",
}

if set(DISPLAY_NAME_BY_NORMALIZED_KEY.keys()) != set(SUPPORTED_BATCH_FOLDER_CATEGORIES):
    raise RuntimeError(
        "DISPLAY_NAME_BY_NORMALIZED_KEY keys must exactly match SUPPORTED_BATCH_FOLDER_CATEGORIES"
    )


def is_supported_batch_folder_category(category_name: str) -> bool:
    """Whether this folder category is implemented for batch processing."""
    return category_name.strip().casefold() in SUPPORTED_BATCH_FOLDER_CATEGORIES


def supported_category_display_names() -> tuple[str, ...]:
    """Sorted display names, e.g. ``(\"DC\",)`` — use in messages and docs."""
    keys = sorted(SUPPORTED_BATCH_FOLDER_CATEGORIES)
    return tuple(DISPLAY_NAME_BY_NORMALIZED_KEY[k] for k in keys)


def describe_supported_categories_for_user() -> str:
    """
    Short sentence listing supported folder categories (for HTTP errors / logs).

    Example: ``Only the "DC" folder category is supported right now``
    """
    labels = supported_category_display_names()
    if not labels:
        return "No folder categories are configured for processing yet."
    if len(labels) == 1:
        return f'Only the "{labels[0]}" folder category is supported right now'
    joined = ", ".join(f'"{label}"' for label in labels)
    return f"Only these folder categories are supported right now: {joined}"


def process_batch_unsupported_categories_message() -> str:
    """Full user-facing detail when the batch has PDFs but none in a supported category."""
    return (
        describe_supported_categories_for_user()
        + " — other folders are shown for your reference but are not processed yet."
    )
