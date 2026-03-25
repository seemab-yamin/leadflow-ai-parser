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
  - **Windows (download JDK):** download an OpenJDK build from **Adoptium (Temurin) JDK 17 (LTS)**:
    - Go to https://adoptium.net/temurin/releases/
    - Choose: `17` (LTS), `JDK`, `Windows`, and `x64`
    - Download the `.msi` installer and install it
    - After installation, verify in a new terminal: `java -version`
    - If `java` is not found, add Java to `PATH`:
      - Find your install folder (commonly something like `C:\Program Files\Eclipse Adoptium\jdk-17.*\`)
      - Add `<JAVA_HOME>\bin` (or the `bin` directory) to `PATH`

## Folder Selection Flow
- **Browser:** the UI uses a folder picker (`webkitdirectory`). It builds a PDF path list and category summary **in the browser** (same rules as the server for supported folders such as `DC`).
- **Upload to server:** the UI uploads eligible PDFs via `POST /api/upload-folder` and receives an `upload_job_id`.
- **Process:** `POST /api/process-batch` sends `root_folder` + `upload_job_id` (preferred) and the server processes the staged PDFs under `outputs/uploads/<upload_job_id>/`.
- **Optional:** `process-batch` can still accept explicit `pdf_paths`, but they must exist on the API host.

## Prompt Versions
- Versioned prompts are stored flat under `prompts/`.
- Runtime picks prompt version from `config.json` key `dc_prompt_version` and loads `prompts/<version>.txt`.

## Running in Development

Same `uvicorn` command as Quickstart. Use a project venv so `tika` and Java match the environment where you run batch jobs.

Optional: verify the AI service is reachable:
- `python scripts/test_ai_service.py`
- `python scripts/test_ai_service.py --model gpt-5.1-2025-11-13`

## Logging (`logs-dir/`)

## Troubleshooting

## Architecture Overview

- **Supported batch folder categories** (e.g. which subfolders like `DC` are processed) live in one place: `app/core/supported_pdf_categories.py`.


## Roadmap

