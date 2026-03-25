# LeadfFlow AI Parser — Project Blueprint

**Purpose:** Local-first web app: user picks a folder of PDFs in the browser, the backend stages files, runs **DC** category extraction (Tika → preprocess → optional OpenAI JSON), and exports an **Excel** workbook with successful rows and per-file failures.

**Audience:** Developers aligning implementation with architecture; pair with `README.md` for day-to-day run instructions.

---

## Goals

1. Serve a Jinja **home page** (`/`) with Tailwind + static JS for folder selection, local path summary, batch progress, and download.
2. **Optional staging** via `app/services/upload_jobs.py` if you add a multipart upload route later (`outputs/uploads/<job_id>/`).
3. **Process** supported PDF paths (today: immediate subfolder **`DC`** per `app/core/supported_pdf_categories.py`) via `run_pdf_batch` and **`POST /api/process-batch`** (`pdf_paths` + `root_folder`).
4. **Extract text** with **Apache Tika** (Java on `PATH`) and run **LLM JSON extraction** using prompts under `prompts/` and `config.json` (`llm_model`, `dc_prompt_version`, optional `dc_min_preprocessed_chars`).
5. **Return** a single `.xlsx` (`outputs/batch/`) and expose **async job status** with **`failed_paths`**, **`pdf_paths_attempted`**, **`pdf_paths_failed`** for transparent UI messaging before download.

## Non-Goals (current phase)

- Production auth / multi-tenant isolation.
- Distributed workers (batch jobs are **in-memory** in `app/services/batch_jobs.py`; replace with Redis/queue when scaling).
- Installers / desktop EXE (separate track).

## Platforms / Run Policy

Develop and run on **macOS, Windows, and Linux**: Python 3.12+, venv, `uvicorn`. **Java** required for Tika-backed PDF text. Optional **`.env`** for secrets (e.g. `OPENAI_API_KEY`); see `app/core/config.py`.

---

## Core User Flow (browser)

1. User opens `/` (FastAPI + Jinja).
2. User chooses a folder (`webkitdirectory`); the SPA builds **`pdf_paths`** and a category summary **in the browser** (aligned with `app/services/pdf_category.py` rules).
3. User runs **`POST /api/process-batch`** with `root_folder` and **`pdf_paths`** → **202** + `job_id`. Paths must **exist on the API host** (relative to server cwd or absolute).
4. UI polls **`GET /api/process-batch/status/{job_id}`** until `completed` or `failed`.
5. On success, UI may **HEAD** verify then **`GET /api/download/batch-output/{filename}`** for the workbook.

**Partial failure:** `status` is still `completed` if the job finished but some PDFs failed; those appear in **`failed_paths`** and in the **FailedPaths** sheet. The UI surfaces errors **before** encouraging download.

**Job failure:** `status` is `failed`; **`error_detail`** + **`message`** explain the outage.

---

## Backend (FastAPI) — Responsibilities

| Area | Responsibility |
|------|----------------|
| **Entry** | `app/main.py`: templates, static mount, middleware logging, routers. |
| **Health** | `GET /health`, `/health/` |
| **Batch** | `POST /api/process-batch`, `GET /api/process-batch/status/{job_id}` |
| **Download** | Batch output under `GET|HEAD /api/download/batch-output/...` (`app/api/download_batch.py`) |
| **PDF pipeline** | `app/services/pdf_batch_processor.py`: dispatch parsers, write xlsx (ParsedRows + FailedPaths). |
| **DC parser Tika** | `app/services/pdf_text/`, `app/services/parsers/dc.py`: preprocess, min text guard, LLM via `app/services/llm_extraction.py`. |
| **Config** | `app/core/config.py` + repo `config.json` + optional `.env`. |
| **Logging** | `app/core/logging_setup.py` → rotating file under `logs-dir/`, logger name `leadfflow`. |
| **Errors** | `app/core/user_friendly_errors.py` for HTTP copy; parsers raise user-facing exceptions captured as **`failed_paths`** rows. |

---

## Frontend (templates + static JS)

- **`app/templates/index.html`** — Shell + regions for categories, batch badge, result / failure alert, download link.
- **`app/static/js/app.js`** — Local folder summary, batch poll (`job_id` only), HEAD verify, download; **`failed_paths`** summary; shared helpers for **FastAPI `detail`** (string / validation array / HTTP fallbacks) and **network** errors; scroll error into view.
- **`app/static/css/styles.css`** — Layout + batch status (including **completed-with-warnings** styling).

---

## Suggested Project Structure (as implemented)

```text
app/
  main.py                      # FastAPI app, static, templates, router includes
  api/
    health.py
    process_batch.py           # process-batch + status
    download_batch.py
    models.py                  # Pydantic: batch request/response models
  core/
    config.py
    logging_setup.py
    supported_pdf_categories.py
    user_friendly_errors.py
  services/
    batch_jobs.py              # In-memory job registry
    pdf_batch_processor.py
    upload_jobs.py
    llm_extraction.py
    pdf_category.py
    parsers/
      dc.py
    pdf_text/                  # Tika-backed extraction + path resolution
  templates/
    index.html
  static/
    css/styles.css
    js/app.js
prompts/                       # e.g. DC_Prob_Prompt_v7.txt
config.json                    # llm_model, dc_prompt_version, optional limits
outputs/
  uploads/<job_id>/           # Staged folder trees
  batch/                      # Generated xlsx exports
logs-dir/
  app.log
scripts/
  test_tika_pdf.py            # Optional Tika smoke test
tests/
  test_process_batch.py
  test_download_batch.py
  test_pdf_text.py
  test_llm_extraction.py
  test_upload_flow.py
requirements.txt
.env.example                  # Local dev env hints
```

---

## Data Contract — Batch status (high level)

**`GET /api/process-batch/status/{job_id}`** (completed):

- `status`, `message`, `root_folder`
- `download_url`, `output_file` when done
- `error_detail` when job-level `failed`
- `failed_paths`: `[{ "pdf_path", "error" }, ...]` (same as FailedPaths sheet)
- `pdf_paths_attempted`, `pdf_paths_failed` for UI copy

**`POST /api/process-batch` body** (`ProcessBatchRequest`): `root_folder`, optional `pdf_paths`.

---

## Logging

- Request middleware + structured lines on `leadfflow`.
- DC/LLM: success and failure with **`pdf_path`** context (no API keys in logs).
- Startup logs `app_env`.

---

## Development Workflow (local)

1. Create venv; install `requirements.txt`.
2. Java on `PATH` for Tika; set **`OPENAI_API_KEY`** / `config.json` for DC LLM.
3. `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
4. Open `http://localhost:8000/` — pick a folder (paths must exist on the server cwd) → process → download.

Optional: `python scripts/test_tika_pdf.py path/to/file.pdf`

---

## Acceptance Criteria (current)

- [x] Server starts; `/` renders; `/health` responds.
- [x] Batch job: **202** → background run → **status** poll → **download** xlsx.
- [x] Excel contains **ParsedRows** and optional **FailedPaths**; API returns **`failed_paths`** and counts for the UI.
- [x] DC path: Tika text → preprocess → minimum length guard → LLM JSON → row expansion; failures recorded per file.
- [x] Frontend shows backend errors in a dedicated alert; handles validation arrays and network errors.

---

*Last revised to match the repository layout and batch/DC pipeline (async job, Excel export, transparent failures).*
