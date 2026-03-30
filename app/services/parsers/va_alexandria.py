"""
VA Alexandria category — parsing for PDFs under a ``VA Alexandria`` folder.

This parser:
- resolves the PDF on disk
- extracts text (Docling backend)
- preprocesses text (remove URLs + timestamp/page header lines)
- runs LLM JSON extraction (VA prompt)
- expands `Heirs` into multiple rows (one row per heir)
"""

from __future__ import annotations

import copy
import re

from app.core.config import settings
from app.core.logging_setup import get_logger
from app.services.llm_extraction import extract_json_with_llm
from app.services.parsers.dc import _clean_phone_number as clean_phone_number
from app.services.pdf_text import extract_text_from_pdf, resolve_batch_pdf_path

logger = get_logger()


class VAExtractedTextError(RuntimeError):
    """Preprocessed PDF text is too short to run VA extraction."""

    def __init__(self, message: str, *, pdf_path: str | None = None) -> None:
        self.pdf_path = pdf_path
        super().__init__(message)


def _user_file_phrase(pdf_path: str) -> str:
    return f'We could not process "{pdf_path}". '


def _preprocess_text(text: str) -> str:
    """Normalize raw extracted text for VA parsing."""
    lines = text.split("\n")
    result: list[str] = []
    url_pattern = re.compile(r"https?://\S+")

    # Only match timestamp format (DD/MM/YYYY, HH:MM) - not bare dates like 08/12/2025.
    # Header/footer "printed on" stamps include time.
    timestamp_pattern = re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{4}\s*,\s*\d{1,2}:\d{2}\s*$")
    page_num_pattern = re.compile(r"^\s*\d+/\d+\s*$")

    for line in lines:
        line = url_pattern.sub("", line).strip()
        if timestamp_pattern.match(line) or page_num_pattern.match(line):
            continue
        if not line:
            continue
        result.append(line)

    # Preserve line breaks for better downstream matching.
    return "\n".join(result).strip()


def _name_key(person: dict) -> str:
    """Deduplication key: First+Last names (case-insensitive)."""
    first = str(person.get("First Name") or "").strip().casefold()
    last = str(person.get("Last Name") or "").strip().casefold()
    return f"{first}::{last}"


def _has_address(person: dict) -> bool:
    """Whether this record contains an address-like value."""
    addr = str(person.get("Address") or "").strip()
    return bool(addr)


def _merge_person_with_address(base: dict, other: dict) -> dict:
    """Merge two person dicts, filling only empty fields from `other`."""
    merged = dict(base)
    for k, v in other.items():
        if merged.get(k) not in (None, ""):
            continue
        if v not in (None, ""):
            merged[k] = v
    return merged


def _build_all_parties(
    party_data: list[dict],
    heirs: list[dict],
    max_heirs: int = 2,
) -> list[dict]:
    """
    Build deduplicated all_parties from party arrays + up to max_heirs heirs.
    When duplicate found (same First+Last name), prefer the one with address as owner.
    """
    all_parties: list[dict] = []
    seen: dict[str, int] = {}  # name_key -> index in all_parties

    for party in party_data:
        key = _name_key(party)
        if key not in seen:
            seen[key] = len(all_parties)
            all_parties.append(party)
        else:
            idx = seen[key]
            existing = all_parties[idx]
            if _has_address(party) and not _has_address(existing):
                all_parties[idx] = party
            elif _has_address(existing) and not _has_address(party):
                all_parties[idx] = _merge_person_with_address(existing, party)
            else:
                all_parties[idx] = _merge_person_with_address(existing, party)

    heirs_added = 0
    for heir in heirs:
        if heirs_added >= max_heirs:
            break
        key = _name_key(heir)
        if key not in seen:
            seen[key] = len(all_parties)
            all_parties.append(heir)
            heirs_added += 1
        else:
            idx = seen[key]
            existing = all_parties[idx]
            if _has_address(heir) and not _has_address(existing):
                all_parties[idx] = heir
            elif _has_address(existing) and not _has_address(heir):
                all_parties[idx] = _merge_person_with_address(existing, heir)
            else:
                all_parties[idx] = _merge_person_with_address(existing, heir)

    return all_parties


def _expand_va_records_from_llm(data: dict) -> list[dict]:
    """Expand VA LLM output into row-friendly records.

    The VA prompt returns a single document JSON object with list fields like `POW`,
    `Subscriber`, and `Heirs`. We normalize the output into row-friendly columns:

    - combine party arrays into one `party_data` list
    - create one row per party (like the DC parser does)
    - flatten heirs into columns like `Heir 1 First Name` on every row
    """

    # Work on a shallow copy since we `pop()` list fields out of the payload.
    data = dict(data)

    party_keys = (
        "Applicants",
        "Administrator",
        "POW",
        "Proponent of Will",
        "Subscriber",
        "Executor",
        "Personal Representative",
    )

    party_data: list[dict] = []
    for key in party_keys:
        items = data.pop(key, [])
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    party_data.append(item)

    heirs = data.pop("Heirs", [])
    if not isinstance(heirs, list):
        heirs = []

    max_heirs = 2

    # Add Heir columns to base data (each record will inherit these) - heirs logic unchanged.
    for i, hr in enumerate(heirs[:max_heirs]):
        if not isinstance(hr, dict):
            continue
        data[f"Heir {i + 1} First Name"] = hr.get("First Name")
        data[f"Heir {i + 1} Last Name"] = hr.get("Last Name")
        data[f"Relationship {i + 1}"] = hr.get("Relationship")
        data[f"Age {i + 1}"] = hr.get("Age")
        data[f"Address {i + 1}"] = hr.get("Address")
        data[f"City {i + 1}"] = hr.get("City")
        data[f"State {i + 1}"] = hr.get("State")
        data[f"Zip {i + 1}"] = hr.get("Zip")

    # Build all_parties with deduplication: add up to 2 heirs, prefer record with address when duplicate.
    all_parties = _build_all_parties(party_data, heirs, max_heirs=max_heirs)

    records: list[dict] = []
    if all_parties:
        for party in all_parties:
            record = copy.deepcopy(data)
            record["Owner 1 First Name"] = party.get("First Name")
            record["Owner 1 Last Name"] = party.get("Last Name")
            record["Owner 2 First Name"] = None
            record["Owner 2 Last Name"] = None
            record["Property Address Line 1"] = party.get("Address")
            record["Property Address Line 2"] = None
            record["Property City"] = party.get("City")
            record["Property State"] = party.get("State")
            record["Property ZIP"] = party.get("Zip")
            record["PR Phone Number"] = clean_phone_number(party.get("Phone Number"))
            records.append(record)
    else:
        # No parties: create one record with null owner/property fields
        record = copy.deepcopy(data)
        record["Owner 1 First Name"] = None
        record["Owner 1 Last Name"] = None
        record["Owner 2 First Name"] = None
        record["Owner 2 Last Name"] = None
        record["Property Address Line 1"] = None
        record["Property Address Line 2"] = None
        record["Property City"] = None
        record["Property State"] = None
        record["Property ZIP"] = None
        record["PR Phone Number"] = None
        records.append(record)

    return records


def parse_va_alexandria(
    pdf_path: str,
    *,
    source_root: str | None = None,
) -> list[dict]:
    """
    Resolve the PDF on disk, extract text, run VA LLM JSON extraction, and return rows.
    """
    path = resolve_batch_pdf_path(pdf_path, source_root=source_root)
    if path is None:
        raise FileNotFoundError(
            "PDF not found on the server for this job. "
            "The upload temp folder may be missing or the path is invalid."
        )

    text = extract_text_from_pdf(str(path), backend="docling")
    text = _preprocess_text(text)

    min_chars = settings.dc_min_preprocessed_chars
    n = len(text)
    if n < min_chars:
        logger.warning(
            "VA PDF preprocessed text too short; skipping LLM pdf_path=%s char_count=%s min_required=%s",
            pdf_path,
            n,
            min_chars,
        )
        raise VAExtractedTextError(
            _user_file_phrase(pdf_path)
            + f"Too little readable text was extracted from this PDF ({n} characters after cleanup; "
            f"at least {min_chars} are required). The file may be scanned without OCR, mostly images, "
            "or not contain enough case text.",
            pdf_path=pdf_path,
        )

    llm_model = settings.llm_model
    llm_data = extract_json_with_llm(
        text,
        llm_model=llm_model,
        prompt_version=settings.va_alexandria_prompt_version,
        pdf_path=pdf_path,
    )

    expanded = _expand_va_records_from_llm(llm_data)
    return [{"pdf_path": pdf_path, **row} for row in expanded]
