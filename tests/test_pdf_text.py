"""PDF path resolution and Tika extraction (mocked where needed)."""

from __future__ import annotations

import pytest

from app.services.pdf_text.backends.tika import extract_text_with_tika
from app.services.pdf_text.paths import resolve_batch_pdf_path

# Default ``dc_min_preprocessed_chars`` is 80; append so mocked extraction still passes the gate.
_DC_TEXT_PAD = "x" * 100


def test_resolve_batch_pdf_path_rejects_parent_segments():
    assert resolve_batch_pdf_path("DC/../secret.pdf") is None


def test_resolve_batch_pdf_path_with_source_root(tmp_path):
    (tmp_path / "DC").mkdir()
    pdf = tmp_path / "DC" / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    resolved = resolve_batch_pdf_path("DC/a.pdf", source_root=str(tmp_path))
    assert resolved == pdf.resolve()


def test_extract_text_with_tika_success(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    calls: list[str] = []

    def fake_from_file(p: str):
        calls.append(p)
        return {"content": "  hello world  \n"}

    out = extract_text_with_tika(str(pdf), _from_file=fake_from_file)

    assert out == "hello world"
    assert len(calls) == 1


def test_extract_text_with_tika_bytes_content(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    out = extract_text_with_tika(
        str(pdf), _from_file=lambda p: {"content": b"byte text"}
    )

    assert out == "byte text"


def test_parse_dc_parser_row(monkeypatch, tmp_path):
    from unittest.mock import patch

    from app.services.parsers.dc import parse_dc_parser

    (tmp_path / "DC").mkdir()
    pdf = tmp_path / "DC" / "case.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with (
        patch(
            "app.services.parsers.dc.extract_text_from_pdf",
            return_value="parcel text" + _DC_TEXT_PAD,
        ) as ext,
        patch(
            "app.services.parsers.dc.extract_json_with_llm",
            return_value={"ok": True},
        ),
    ):
        rows = parse_dc_parser("DC/case.pdf", source_root=str(tmp_path))

    ext.assert_called_once_with(str(pdf.resolve()), backend="tika")
    assert rows[0]["pdf_path"] == "DC/case.pdf"
    assert rows[0]["ok"] is True


def test_parse_dc_parser_file_not_found():
    from app.services.parsers.dc import parse_dc_parser

    with pytest.raises(FileNotFoundError, match="upload temp folder"):
        parse_dc_parser("DC/missing.pdf")


def test_parse_dc_parser_rejects_insufficient_preprocessed_text(caplog, tmp_path):
    from unittest.mock import patch

    from app.services.parsers.dc import DCExtractedTextError, parse_dc_parser

    (tmp_path / "DC").mkdir()
    pdf = tmp_path / "DC" / "thin.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with caplog.at_level("WARNING"):
        with (
            patch("app.services.parsers.dc.extract_text_from_pdf", return_value="tiny"),
            patch("app.services.parsers.dc.extract_json_with_llm") as llm,
        ):
            with pytest.raises(DCExtractedTextError, match="Too little readable text"):
                parse_dc_parser("DC/thin.pdf", source_root=str(tmp_path))
    llm.assert_not_called()
    assert "preprocessed text too short" in caplog.text
    assert "DC/thin.pdf" in caplog.text


def test_parse_dc_parser_applies_preprocessing(monkeypatch, tmp_path):
    from unittest.mock import patch

    from app.services.parsers.dc import parse_dc_parser

    (tmp_path / "DC").mkdir()
    pdf = tmp_path / "DC" / "case.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    raw = (
        "Top\n"
        "Register of Actions - should drop\n"
        "See https://example.com now\n"
        "Many   spaces\n"
    ) + _DC_TEXT_PAD
    with (
        patch("app.services.parsers.dc.extract_text_from_pdf", return_value=raw),
        patch("app.services.parsers.dc.extract_json_with_llm", return_value={}) as llm,
    ):
        rows = parse_dc_parser("DC/case.pdf", source_root=str(tmp_path))

    llm.assert_called_once()
    assert llm.call_args.args[0] == "Top\nSee now\nMany spaces\n" + _DC_TEXT_PAD
    assert rows[0]["pdf_path"] == "DC/case.pdf"


def test_parse_dc_parser_runs_llm_after_preprocess(monkeypatch, tmp_path):
    from unittest.mock import patch

    from app.services.parsers.dc import parse_dc_parser

    (tmp_path / "DC").mkdir()
    pdf = tmp_path / "DC" / "case.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    with (
        patch(
            "app.services.parsers.dc.extract_text_from_pdf",
            return_value="A  line https://a.com\nRegister of Actions - drop\nB"
            + _DC_TEXT_PAD,
        ),
        patch(
            "app.services.parsers.dc.extract_json_with_llm",
            return_value={"ok": True},
        ) as llm,
    ):
        rows = parse_dc_parser("DC/case.pdf", source_root=str(tmp_path))

    llm.assert_called_once()
    args = llm.call_args.args
    assert args[0] == "A line \nB" + _DC_TEXT_PAD
    assert rows[0]["pdf_path"] == "DC/case.pdf"
    assert rows[0]["ok"] is True


def test_parse_dc_parser_expands_parties_and_heirs(tmp_path):
    from unittest.mock import patch

    from app.services.parsers.dc import parse_dc_parser

    (tmp_path / "DC").mkdir()
    pdf = tmp_path / "DC" / "case.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    llm_json = {
        "Case Number": "X1",
        "Applicants": [
            {
                "First Name": "John",
                "Last Name": "Doe",
                "Address": "123 A St",
                "City": "DC",
                "State": "DC",
                "Zip": "20001",
                "Phone Number": "(202) 555-9898",
            }
        ],
        "Heirs": [
            {
                "First Name": "Kid",
                "Last Name": "Doe",
                "Relationship": "Child",
                "Age": "12",
                "Address": "1 B St",
                "City": "DC",
                "State": "DC",
                "Zip": "20002",
            }
        ],
    }
    with (
        patch(
            "app.services.parsers.dc.extract_text_from_pdf",
            return_value="abc" + _DC_TEXT_PAD,
        ),
        patch("app.services.parsers.dc.extract_json_with_llm", return_value=llm_json),
    ):
        rows = parse_dc_parser("DC/case.pdf", source_root=str(tmp_path))

    assert len(rows) == 1
    r = rows[0]
    assert r["Owner 1 First Name"] == "John"
    assert r["Property ZIP"] == "20001"
    assert r["PR Phone Number"] == "2025559898"
    assert r["Heir 1 First Name"] == "Kid"
    assert r["Relationship 1"] == "Child"


def test_extract_text_with_docling_backend_mocked(tmp_path, monkeypatch):
    import importlib
    import sys
    import types

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    class _FakeDocument:
        def export_to_markdown(self):
            return "  hello docling  \n"

    class _FakeResult:
        document = _FakeDocument()

    class _FakeDocumentConverter:
        def convert(self, pdf_path: str):
            # Mirror the expected shape used by the backend.
            assert pdf_path == str(pdf.resolve())
            return _FakeResult()

    fake_pkg = types.ModuleType("docling")
    fake_dc = types.ModuleType("docling.document_converter")
    fake_dc.DocumentConverter = _FakeDocumentConverter

    monkeypatch.setitem(sys.modules, "docling", fake_pkg)
    monkeypatch.setitem(sys.modules, "docling.document_converter", fake_dc)

    # `docling.py` imports DocumentConverter at module load; patch first, then reload
    # so tests that already imported the real converter still see the fake.
    import app.services.pdf_text.backends.docling as docling_backend
    import app.services.pdf_text.extraction as extraction_mod

    importlib.reload(docling_backend)
    importlib.reload(extraction_mod)

    out = extraction_mod.extract_text_from_pdf(str(pdf), backend="docling")
    assert out == "hello docling"
