"""
Batch folder workflow — **contract & vocabulary** (source of truth for UX + API shape).

This module documents the target behavior while the legacy path-inference pipeline
is retired. Implementers should follow ``todo.md`` for ordered tasks.

Vocabulary
----------

**Pick root**
    Directory the user selects in the browser. Referenced in API bodies as
    ``root_folder`` (its display name / basename).

**Category folder**
    An **immediate child** of the pick root (e.g. ``DC``, ``VA Alexandria``).
    Any name is allowed; the UI lists every such folder as a *document category*.
    There is **no** hardcoded list of “allowed category folder names” in this
    contract.

**Bucket (processing unit)**
    An **immediate child** of a category folder. The UI lists buckets per category;
    the user **selects which buckets** to include before proceeding.

**Parser implementation key**
    Internal key for code that turns PDFs into rows (e.g. ``dc``). Mapping from
    a user’s category folder name → parser key is **explicit configuration or
    convention** (see ``app.core.supported_pdf_categories``), *not* inference
    from arbitrary path shape beyond what the user selected.

Target API (process batch)
---------------------------

Browser flow will send, in addition to ``root_folder`` and ``upload_job_id``:

.. code-block:: json

    {
      "root_folder": "My Matter Folder",
      "upload_job_id": "...",
      "selection": [
        { "category": "DC", "subfolders": ["", "2026"] },
        { "category": "VA Alexandria", "subfolders": ["Circuit"] }
      ]
    }

Use an empty string ``""`` in ``subfolders`` for PDFs that live **directly** in the
category folder (not inside a named subfolder).

The backend **expands** ``selection`` to concrete PDF paths under the staged
upload tree, then dispatches each file using the parser keyed for that category.
``pdf_paths`` + path-derived category guessing become **legacy / optional** only.

Out of scope for this module
-----------------------------

* Excel shape, job polling, upload staging paths (unchanged mechanically).
* Concrete UI components (checkboxes, per-category panels) — see ``todo.md``.
"""

from __future__ import annotations

__all__: list[str] = []
