"""Batch flow tests that mirror browser-relative paths resolved from cwd."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _wait_completed(job_id: str) -> dict:
    for _ in range(50):
        r = client.get(f"/api/process-batch/status/{job_id}")
        assert r.status_code == 200
        data = r.json()
        if data["status"] in ("completed", "failed"):
            return data
    raise AssertionError("job did not finish")


def test_process_batch_accepts_pdf_paths_relative_to_server_cwd(tmp_path, monkeypatch):
    """Paths must exist on the API server; cwd is set to a temp tree for this test."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "DC").mkdir()
    (tmp_path / "DC" / "case.pdf").write_bytes(b"%PDF-1.4")

    proc = client.post(
        "/api/process-batch",
        json={
            "root_folder": "batch-root",
            "pdf_paths": ["DC/case.pdf"],
        },
    )
    assert proc.status_code == 202
    done = _wait_completed(proc.json()["job_id"])
    assert done["status"] == "completed"
    assert done.get("pdf_paths_attempted") == 1
    assert isinstance(done.get("failed_paths"), list)
    assert done["download_url"].startswith("/api/download/batch-output/")


def test_upload_folder_stages_files_and_returns_upload_job_id():
    """Browser upload should stage files under outputs/uploads/<upload_job_id>/."""
    up = client.post(
        "/api/upload-folder",
        data={"root_folder_name": "MyPick"},
        files=[
            (
                "files",
                ("MyPick/DC/case.pdf", b"%PDF-1.4", "application/pdf"),
            )
        ],
    )
    assert up.status_code == 200
    body = up.json()
    assert isinstance(body.get("upload_job_id"), str)
    assert isinstance(body.get("pdf_paths_saved"), int)
    assert body.get("pdf_paths_saved") == 1
    assert isinstance(body.get("staging_dir"), str)
    assert "outputs/uploads" in body["staging_dir"]


def test_filter_pdf_paths_existing_under_staged_dir():
    from app.services.upload_jobs import (
        create_upload_job_dir,
        filter_pdf_paths_existing_under_staged_dir,
    )

    _job_id, job_dir = create_upload_job_dir()
    (job_dir / "DC" / "sub").mkdir(parents=True)
    (job_dir / "DC" / "sub" / "a.pdf").write_bytes(b"%PDF-1.4")
    (job_dir / "DC" / "b.pdf").write_bytes(b"%PDF-1.4")

    out = filter_pdf_paths_existing_under_staged_dir(
        job_dir,
        ["Pick/DC/sub/a.pdf", "Pick/DC/b.pdf", "bogus/x.pdf"],
        "Pick",
    )
    assert set(out) == {"DC/sub/a.pdf", "DC/b.pdf"}


def test_expand_selection_to_staged_pdf_paths():
    from app.services.upload_jobs import (
        create_upload_job_dir,
        expand_selection_to_staged_pdf_paths,
    )

    _job_id, job_dir = create_upload_job_dir()
    (job_dir / "DC" / "2026").mkdir(parents=True)
    (job_dir / "DC" / "2026" / "a.pdf").write_bytes(b"%PDF-1.4")
    (job_dir / "DC" / "b.pdf").write_bytes(b"%PDF-1.4")
    (job_dir / "loose.pdf").write_bytes(b"%PDF-1.4")

    pairs, err = expand_selection_to_staged_pdf_paths(
        job_dir,
        [("DC", ["", "2026"]), ("(root)", [""])],
    )
    assert err is None
    by_path = dict(pairs)
    assert set(by_path) == {"DC/b.pdf", "DC/2026/a.pdf", "loose.pdf"}
    assert by_path["DC/b.pdf"] == "DC"
    assert by_path["DC/2026/a.pdf"] == "DC"
    assert by_path["loose.pdf"] == "(root)"


def test_expand_selection_preserves_client_category_label_for_parser_routing():
    """Disk folder may differ in case; category label for parser should stay the client's string."""
    from app.services.upload_jobs import (
        create_upload_job_dir,
        expand_selection_to_staged_pdf_paths,
    )

    _job_id, job_dir = create_upload_job_dir()
    (job_dir / "dc" / "b").mkdir(parents=True)
    (job_dir / "dc" / "b" / "x.pdf").write_bytes(b"%PDF-1.4")

    pairs, err = expand_selection_to_staged_pdf_paths(
        job_dir,
        [("DC", ["b"])],
    )
    assert err is None
    assert len(pairs) == 1
    rel, cat = pairs[0]
    assert rel.replace("\\", "/").casefold() == "dc/b/x.pdf".casefold()
    assert cat == "DC"


def test_category_for_staging_relative_pdf_path():
    from app.services.upload_jobs import category_for_staging_relative_pdf_path

    assert category_for_staging_relative_pdf_path("a.pdf") == "(root)"
    assert category_for_staging_relative_pdf_path("DC/x.pdf") == "DC"
    assert category_for_staging_relative_pdf_path("DC/sub/y.pdf") == "DC"


def test_process_batch_upload_job_respects_selection_subset():
    up = client.post(
        "/api/upload-folder",
        data={"root_folder_name": "MyPick"},
        files=[
            (
                "files",
                ("MyPick/DC/bucket_a/one.pdf", b"%PDF-1.4", "application/pdf"),
            ),
            (
                "files",
                ("MyPick/DC/bucket_b/two.pdf", b"%PDF-1.4", "application/pdf"),
            ),
        ],
    )
    assert up.status_code == 200
    upload_job_id = up.json()["upload_job_id"]

    proc = client.post(
        "/api/process-batch",
        json={
            "root_folder": "MyPick",
            "upload_job_id": upload_job_id,
            "selection": [{"category": "DC", "subfolders": ["bucket_a"]}],
        },
    )
    assert proc.status_code == 202
    done = _wait_completed(proc.json()["job_id"])
    assert done["status"] == "completed"
    assert done.get("pdf_paths_attempted") == 1


def test_process_batch_upload_job_legacy_pdf_paths_subset_still_works():
    up = client.post(
        "/api/upload-folder",
        data={"root_folder_name": "MyPick"},
        files=[
            (
                "files",
                ("MyPick/DC/one.pdf", b"%PDF-1.4", "application/pdf"),
            ),
            (
                "files",
                ("MyPick/DC/two.pdf", b"%PDF-1.4", "application/pdf"),
            ),
        ],
    )
    assert up.status_code == 200
    upload_job_id = up.json()["upload_job_id"]

    proc = client.post(
        "/api/process-batch",
        json={
            "root_folder": "MyPick",
            "upload_job_id": upload_job_id,
            "pdf_paths": ["MyPick/DC/one.pdf"],
        },
    )
    assert proc.status_code == 202
    done = _wait_completed(proc.json()["job_id"])
    assert done["status"] == "completed"
    assert done.get("pdf_paths_attempted") == 1


def test_process_batch_selection_unknown_bucket_400():
    up = client.post(
        "/api/upload-folder",
        data={"root_folder_name": "MyPick"},
        files=[
            (
                "files",
                ("MyPick/DC/case.pdf", b"%PDF-1.4", "application/pdf"),
            ),
        ],
    )
    assert up.status_code == 200
    upload_job_id = up.json()["upload_job_id"]

    proc = client.post(
        "/api/process-batch",
        json={
            "root_folder": "MyPick",
            "upload_job_id": upload_job_id,
            "selection": [{"category": "DC", "subfolders": ["missing-bucket"]}],
        },
    )
    assert proc.status_code == 400
    assert "not found" in proc.json().get("detail", "").lower()


def test_process_batch_selection_no_implemented_parser_400():
    up = client.post(
        "/api/upload-folder",
        data={"root_folder_name": "MyPick"},
        files=[
            (
                "files",
                ("MyPick/Other/case.pdf", b"%PDF-1.4", "application/pdf"),
            ),
        ],
    )
    assert up.status_code == 200
    upload_job_id = up.json()["upload_job_id"]

    proc = client.post(
        "/api/process-batch",
        json={
            "root_folder": "MyPick",
            "upload_job_id": upload_job_id,
            "selection": [{"category": "Other", "subfolders": [""]}],
        },
    )
    assert proc.status_code == 400
    detail = proc.json().get("detail", "")
    assert "Other" in detail or "without a parser" in detail


def test_process_batch_selection_requires_upload_job_id_422():
    r = client.post(
        "/api/process-batch",
        json={
            "root_folder": "MyPick",
            "selection": [{"category": "DC", "subfolders": [""]}],
        },
    )
    assert r.status_code == 422


def test_process_batch_with_upload_job_id_processes_staged_pdfs():
    up = client.post(
        "/api/upload-folder",
        data={"root_folder_name": "MyPick"},
        files=[
            (
                "files",
                ("MyPick/DC/case.pdf", b"%PDF-1.4", "application/pdf"),
            )
        ],
    )
    assert up.status_code == 200
    upload_job_id = up.json()["upload_job_id"]

    proc = client.post(
        "/api/process-batch",
        json={"root_folder": "MyPick", "upload_job_id": upload_job_id},
    )
    assert proc.status_code == 202
    done = _wait_completed(proc.json()["job_id"])
    assert done["status"] == "completed"
    assert done.get("pdf_paths_attempted") == 1
    assert done.get("download_url")
