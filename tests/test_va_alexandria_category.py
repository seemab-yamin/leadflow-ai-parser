from __future__ import annotations


def test_resolve_parser_key_for_user_category_folder_va_alexandria_case_insensitive():
    from app.core.supported_pdf_categories import (
        resolve_parser_key_for_user_category_folder,
    )

    assert (
        resolve_parser_key_for_user_category_folder("VA Alexandria") == "va_alexandria"
    )
    assert (
        resolve_parser_key_for_user_category_folder("va alexandria") == "va_alexandria"
    )


def test_get_parser_for_category_va_alexandria_returns_callable():
    from app.services.parsers import get_parser_for_category

    fn = get_parser_for_category("VA Alexandria")
    assert fn is not None


def test_parse_va_alexandria_returns_row(tmp_path, monkeypatch):
    from app.services.parsers.va_alexandria import parse_va_alexandria

    (tmp_path / "VA Alexandria").mkdir()
    pdf = tmp_path / "VA Alexandria" / "case.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    def fake_extract_text(pdf_path: str, *, backend: str | None = None) -> str:
        assert backend == "docling"
        assert pdf_path == str(pdf.resolve())
        return "x" * 200

    def fake_extract_json_with_llm(
        text: str, *, llm_model: str, prompt_version: str, pdf_path: str | None = None
    ):
        return {"Document ID": "DOC-1", "prompt_version": prompt_version, "Heirs": []}

    monkeypatch.setattr(
        "app.services.parsers.va_alexandria.extract_text_from_pdf",
        fake_extract_text,
    )
    monkeypatch.setattr(
        "app.services.parsers.va_alexandria.extract_json_with_llm",
        fake_extract_json_with_llm,
    )

    rows = parse_va_alexandria("VA Alexandria/case.pdf", source_root=str(tmp_path))
    assert len(rows) == 1
    assert rows[0]["pdf_path"] == "VA Alexandria/case.pdf"
    assert rows[0]["Document ID"] == "DOC-1"


def test_parse_va_alexandria_expands_parties_and_flattens_heirs(tmp_path, monkeypatch):
    from app.services.parsers.va_alexandria import parse_va_alexandria

    (tmp_path / "VA Alexandria").mkdir()
    pdf = tmp_path / "VA Alexandria" / "case.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    def fake_extract_text(pdf_path: str, *, backend: str | None = None) -> str:
        assert backend == "docling"
        assert pdf_path == str(pdf.resolve())
        return "x" * 200

    def fake_extract_json_with_llm(
        text: str, *, llm_model: str, prompt_version: str, pdf_path: str | None = None
    ):
        return {
            "Document ID": "DOC-1",
            "prompt_version": prompt_version,
            "POW": [
                {
                    "First Name": "P1",
                    "Last Name": "L1",
                    "Address": "1 A St",
                    "City": "Alexandria",
                    "State": "VA",
                    "Zip": "22314",
                    "Phone Number": "5551234567",
                },
                {
                    "First Name": "P2",
                    "Last Name": "L2",
                    "Address": "2 B St",
                    "City": "Alexandria",
                    "State": "VA",
                    "Zip": "22315",
                    "Phone Number": "5552345678",
                },
            ],
            "Heirs": [
                {
                    "First Name": "A",
                    "Last Name": "B",
                    "Relationship": "Child",
                    "Age": "10",
                    "Address": "3 C St",
                    "City": "Alexandria",
                    "State": "VA",
                    "Zip": "22316",
                },
                {
                    "First Name": "C",
                    "Last Name": "D",
                    "Relationship": "Spouse",
                    "Age": "40",
                    "Address": "4 D St",
                    "City": "Alexandria",
                    "State": "VA",
                    "Zip": "22317",
                },
            ],
        }

    monkeypatch.setattr(
        "app.services.parsers.va_alexandria.extract_text_from_pdf",
        fake_extract_text,
    )
    monkeypatch.setattr(
        "app.services.parsers.va_alexandria.extract_json_with_llm",
        fake_extract_json_with_llm,
    )

    rows = parse_va_alexandria("VA Alexandria/case.pdf", source_root=str(tmp_path))
    # 2 POW parties + up to 2 heirs => 4 rows.
    assert len(rows) == 4
    assert rows[0]["pdf_path"] == "VA Alexandria/case.pdf"
    assert rows[0]["Owner 1 First Name"] == "P1"
    assert rows[1]["Owner 1 First Name"] == "P2"
    assert rows[2]["Owner 1 First Name"] == "A"
    assert rows[3]["Owner 1 First Name"] == "C"
    # Heir columns are flattened into every row.
    assert rows[0]["Heir 1 First Name"] == "A"
    assert rows[0]["Heir 2 Last Name"] == "D"
