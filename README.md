# LeadfFlow AI Parser

## Quickstart (about 1 minute)
1. Create and activate a virtual environment:
   - `python -m venv .venv`
   - **macOS / Linux:** `source .venv/bin/activate`
   - **Windows (cmd):** `.venv\Scripts\activate.bat`
   - **Windows (PowerShell):** `.venv\Scripts\Activate.ps1`
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Configure environment (optional): create a `.env` in the repo root if you use env-based secrets (e.g. `OPENAI_API_KEY`); see `app/core/config.py` for supported variables.
4. Start the dev server:
   - `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
5. Open in your browser:
   - `http://localhost:8000/`
   - Health check (liveness): `http://localhost:8000/health` or `http://localhost:8000/health/`

## Requirements

- **Python 3.12+** (see `requirements.txt`).
- **Java (JRE/JDK)** on the server if you run DC PDF text extraction: Apache Tika is used via the `tika` package and shells out to Java. Ensure `java` is on `PATH`.
- **Batch PDFs on disk:** `POST /api/process-batch` accepts `root_folder` plus `pdf_paths` for PDFs that **exist on the API server** (relative paths are resolved from the server process working directory, or use absolute paths).

## Folder Selection Flow
- **Browser:** the UI uses a folder picker (`webkitdirectory`). It builds a PDF path list and category summary **in the browser** (same rules as the server for supported folders such as `DC`).
- **Process:** `POST /api/process-batch` sends those `pdf_paths` and `root_folder`. The server must be able to open each path (e.g. run the app with its cwd set to a folder tree that mirrors the picked layout, or use absolute server paths).
- **Staged uploads:** helpers under `outputs/uploads/` (`app/services/upload_jobs.py`) exist for a future multipart upload route if you add one to `main.py`.

## Prompt Versions
- Versioned prompts are stored flat under `prompts/`.
- Runtime picks prompt version from `config.json` key `dc_prompt_version` and loads `prompts/<version>.txt`.

## Running in Development

Same `uvicorn` command as Quickstart. Use a project venv so `tika` and Java match the environment where you run batch jobs.

## Logging (`logs-dir/`)

## Troubleshooting

## Architecture Overview

- **Supported batch folder categories** (e.g. which subfolders like `DC` are processed) live in one place: `app/core/supported_pdf_categories.py`.


## Roadmap

