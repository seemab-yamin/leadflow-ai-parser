"""
DC category — parsing for PDFs under a ``DC`` folder.

Text is extracted via Apache Tika (:mod:`app.services.pdf_text.backends.tika`).
"""

from __future__ import annotations

import copy
import re

from app.core.config import settings
from app.core.logging_setup import get_logger
from app.services.llm_extraction import extract_json_with_llm
from app.services.pdf_text import extract_text_from_pdf, resolve_batch_pdf_path

logger = get_logger()


class DCExtractedTextError(RuntimeError):
    """Preprocessed PDF text is too short to run DC extraction (user-facing message in args)."""

    def __init__(self, message: str, *, pdf_path: str | None = None) -> None:
        self.pdf_path = pdf_path
        super().__init__(message)


def _user_file_phrase(pdf_path: str) -> str:
    return f'We could not process "{pdf_path}". '


def _preprocess_text(text: str) -> str:
    """Normalize raw extracted text before downstream parsing."""
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r" +", " ", text)
    lines = [line for line in text.split("\n") if "Register of Actions -" not in line]
    return "\n".join(lines).strip()


def _clean_phone_number(value: str | None) -> str | None:
    if value is None:
        return None
    s = re.sub(r"\D+", "", str(value))
    if not s:
        return None
    if len(s) == 11 and s.startswith("1"):
        s = s[1:]
    return s


def _expand_dc_records_from_llm(data: dict) -> list[dict]:
    # Pop party arrays and Heirs - expand into one record per party
    party_keys = (
        "Applicants",
        "Administrator",
        "POW",
        "Subscriber",
        "Executor",
        "Personal Representative",
    )
    all_parties: list[dict] = []
    for key in party_keys:
        items = data.pop(key, [])
        if isinstance(items, list):
            all_parties.extend(items)
    heirs = data.pop("Heirs", [])
    if not isinstance(heirs, list):
        heirs = []

    # Add Heir columns to base data (each record inherits these)
    for i, hr in enumerate(heirs):
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

    records: list[dict] = []
    if all_parties:
        for party in all_parties:
            if not isinstance(party, dict):
                continue
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
            record["PR Phone Number"] = _clean_phone_number(party.get("Phone Number"))
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


def parse_dc_parser(pdf_path: str, *, source_root: str | None = None) -> list[dict]:
    """
    Resolve the PDF on disk, extract text with Tika, and return one result row.

    Parameters
    ----------
    pdf_path
        PDF path from upload/listing flow.
    source_root
        Absolute directory containing uploaded files for this processing job.

    Returns
    -------
    list[dict]
        One or more rows per DC case (parties expansion), each including ``pdf_path``.

    Raises
    ------
    FileNotFoundError
        If the PDF cannot be resolved on disk.
    DCExtractedTextError
        If preprocessed text is shorter than ``settings.dc_min_preprocessed_chars``.
    LLMExtractionError
        If AI extraction fails; the message includes ``pdf_path`` for batch exports and UIs.
    """
    path = resolve_batch_pdf_path(pdf_path, source_root=source_root)
    if path is None:
        raise FileNotFoundError(
            "PDF not found on the server for this job. "
            "The upload temp folder may be missing or the path is invalid."
        )

    text = extract_text_from_pdf(str(path), backend="tika")
    text = _preprocess_text(text)
    min_chars = settings.dc_min_preprocessed_chars
    n = len(text)
    if n < min_chars:
        # Stop here: do not call the LLM. Batch layer records this in failed_paths and the
        # status API returns it so the front end can show which file failed.
        logger.warning(
            "DC PDF preprocessed text too short; skipping LLM pdf_path=%s char_count=%s min_required=%s",
            pdf_path,
            n,
            min_chars,
        )
        raise DCExtractedTextError(
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
        prompt_version=settings.dc_prompt_version,
        pdf_path=pdf_path,
    )
    expanded = _expand_dc_records_from_llm(copy.deepcopy(llm_data))
    return [{"pdf_path": pdf_path, **record} for record in expanded]
