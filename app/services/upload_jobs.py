from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

_REPO_ROOT = Path(__file__).resolve().parents[2]
_UPLOAD_ROOT = _REPO_ROOT / "outputs" / "uploads"


def upload_jobs_root() -> Path:
    _UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    return _UPLOAD_ROOT.resolve()


def create_upload_job_dir() -> tuple[str, Path]:
    job_id = uuid.uuid4().hex
    job_dir = upload_jobs_root() / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    return job_id, job_dir


def get_upload_job_dir(job_id: str) -> Path | None:
    root = upload_jobs_root()
    candidate = (root / job_id).resolve()
    if candidate == root or root not in candidate.parents:
        return None
    if not candidate.is_dir():
        return None
    return candidate


def _sanitize_pdf_path(pdf_path: str, root_folder_name: str | None) -> Path:
    normalized = (pdf_path or "").replace("\\", "/").strip().lstrip("/")
    parts = [p for p in normalized.split("/") if p and p != "."]
    if ".." in parts:
        raise ValueError("Path traversal is not allowed.")
    if not parts:
        raise ValueError("Empty uploaded filename path.")
    if root_folder_name and parts[0].casefold() == root_folder_name.strip().casefold():
        parts = parts[1:]
    if not parts:
        raise ValueError("Invalid uploaded filename path.")
    return Path(*parts)


async def save_uploaded_folder_files(
    *,
    job_dir: Path,
    root_folder_name: str,
    files: list[UploadFile],
) -> list[str]:
    saved_pdf_paths: list[str] = []
    for f in files:
        rel = _sanitize_pdf_path(f.filename or "", root_folder_name)
        if rel.suffix.lower() != ".pdf":
            await f.close()
            continue
        target = (job_dir / rel).resolve()
        if target == job_dir or job_dir not in target.parents:
            raise ValueError("Invalid upload path.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as out:
            while True:
                chunk = await f.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
        await f.close()
        saved_pdf_paths.append(str(rel).replace(os.sep, "/"))
    return saved_pdf_paths


def delete_upload_job_dir(job_id: str) -> None:
    d = get_upload_job_dir(job_id)
    if not d:
        return
    shutil.rmtree(d, ignore_errors=True)


def list_pdf_paths(job_dir: Path) -> list[str]:
    out: list[str] = []
    root = job_dir.resolve()
    for dirpath, _, filenames in os.walk(root):
        d = Path(dirpath)
        for fn in filenames:
            rel = (d / fn).resolve().relative_to(root)
            if rel.suffix.lower() == ".pdf":
                out.append(str(rel).replace(os.sep, "/"))
    return out

