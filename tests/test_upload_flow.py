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
