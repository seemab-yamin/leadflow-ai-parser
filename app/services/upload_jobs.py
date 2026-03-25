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


def category_for_staging_relative_pdf_path(rel_path: str) -> str:
    """
    Category folder label for a path **relative to the upload job dir** (no pick-root prefix).

    * ``x.pdf`` → ``"(root)"``
    * ``DC/case.pdf`` or ``DC/sub/x.pdf`` → ``DC`` (first segment, filesystem casing).
    """
    rel = (rel_path or "").replace("\\", "/").strip().lstrip("/")
    parts = [p for p in rel.split("/") if p and p != "."]
    if ".." in parts:
        return "(root)"
    if len(parts) <= 1:
        return "(root)"
    return parts[0]


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


def normalize_upload_relative_pdf_path(pdf_path: str, root_folder: str) -> str | None:
    """
    Turn a browser-style or staging-relative path into a path relative to the upload job dir.

    Staged files omit the pick-root prefix (e.g. ``DC/case.pdf``). Clients may send
    ``MyPick/DC/case.pdf`` — strip ``root_folder`` when it matches the first segment.
    """
    normalized = (pdf_path or "").replace("\\", "/").strip().lstrip("/")
    parts = [p for p in normalized.split("/") if p and p != "."]
    if ".." in parts:
        return None
    if not parts:
        return None
    if parts[0].casefold() == root_folder.strip().casefold():
        parts = parts[1:]
    if not parts:
        return None
    rel = "/".join(parts)
    if not rel.lower().endswith(".pdf"):
        return None
    return rel


def _resolve_child_dir_casefold(parent: Path, segment: str) -> Path | None:
    """Return a direct child directory of ``parent`` whose name matches ``segment`` (casefold)."""
    want = segment.strip().casefold()
    if not want:
        return None
    try:
        for child in parent.iterdir():
            if child.is_dir() and child.name.casefold() == want:
                resolved = child.resolve()
                if resolved == parent or parent not in resolved.parents:
                    continue
                return resolved
    except OSError:
        return None
    return None


def expand_selection_to_staged_pdf_paths(
    job_dir: Path,
    selection: list[tuple[str, list[str]]],
) -> tuple[list[tuple[str, str]], str | None]:
    """
    Expand API ``selection`` to ``(staging-relative path, category folder label)`` pairs.

    The **category** string is the client-provided category name (e.g. ``DC``), used for
    parser routing — not re-inferred from the path alone.

    * ``subfolder == ""`` means PDFs directly under ``<category>/*.pdf`` (not in a subfolder).
    * Any other subfolder name must exist as a directory under ``<category>/`` on disk.

    Returns ``(pairs, error)`` where ``error`` is a user-facing message on failure.
    """
    job_root = job_dir.resolve()
    if not job_root.is_dir():
        return [], "Invalid upload directory."

    all_staged = list_pdf_paths(job_dir)
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    for category_raw, subfolders in selection:
        cat_label = category_raw.strip()
        if not cat_label:
            return [], "Each selection entry must include a non-empty category name."

        if cat_label == "(root)":
            for sf in subfolders:
                if sf != "":
                    return (
                        [],
                        'Category "(root)" only supports the direct bucket (use an empty subfolder name).',
                    )
            for rel in all_staged:
                if "/" in rel or not rel.lower().endswith(".pdf"):
                    continue
                if rel not in seen:
                    seen.add(rel)
                    out.append((rel, "(root)"))
            continue

        cat_dir = _resolve_child_dir_casefold(job_root, cat_label)
        if cat_dir is None or not cat_dir.is_dir():
            return (
                [],
                f'Category folder "{cat_label}" was not found under this upload.',
            )
        cat_actual = cat_dir.name

        for sf in subfolders:
            if sf == "":
                for rel in all_staged:
                    parts = rel.split("/")
                    if len(parts) != 2 or not parts[1].lower().endswith(".pdf"):
                        continue
                    if parts[0].casefold() != cat_actual.casefold():
                        continue
                    if rel not in seen:
                        seen.add(rel)
                        out.append((rel, cat_label))
                continue

            bucket_dir = _resolve_child_dir_casefold(cat_dir, sf)
            if bucket_dir is None or not bucket_dir.is_dir():
                return (
                    [],
                    f'Bucket folder "{sf}" was not found under category "{cat_label}" '
                    "in this upload.",
                )
            bucket_actual = bucket_dir.name
            needle = f"{cat_actual}/{bucket_actual}/"
            for rel in all_staged:
                if (
                    len(rel) > len(needle)
                    and rel.casefold().startswith(needle.casefold())
                    and rel not in seen
                ):
                    seen.add(rel)
                    out.append((rel, cat_label))

    return out, None


def filter_pdf_paths_existing_under_staged_dir(
    job_dir: Path,
    paths: list[str],
    root_folder: str,
) -> list[str]:
    """
    Keep only paths that resolve to an existing file under ``job_dir``.

    Unknown or unsafe paths are skipped (caller may treat empty result as error).
    """
    root = job_dir.resolve()
    allowed = set(list_pdf_paths(job_dir))
    out: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        rel = normalize_upload_relative_pdf_path(raw, root_folder)
        if rel is None or rel not in allowed:
            continue
        target = (job_dir / Path(*rel.split("/"))).resolve()
        if target != root and root in target.parents and target.is_file():
            if rel not in seen:
                seen.add(rel)
                out.append(rel)
    return out

