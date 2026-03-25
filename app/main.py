import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.download_batch import router as download_batch_router
from app.api.health import router as health_router
from app.api.process_batch import router as process_batch_router
from app.core.config import settings
from app.core.logging_setup import configure_logging, http_request_logging_middleware

app = FastAPI(title="LeadfFlow AI Parser")

app.include_router(health_router, prefix="/health")
app.include_router(process_batch_router, prefix="/api")
app.include_router(download_batch_router, prefix="/api")

templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent / "templates")
)
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    """Browsers request /favicon.ico by default; serve our SVG with an SVG media type."""
    return FileResponse(
        path=str(static_dir / "favicon.svg"),
        media_type="image/svg+xml",
    )


@app.on_event("startup")
def _startup() -> None:
    configure_logging()
    logging.getLogger("leadfflow").info("app_startup app_env=%s", settings.app_env)


@app.middleware("http")
async def _log_requests(request: Request, call_next):
    return await http_request_logging_middleware(request, call_next)


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    return templates.TemplateResponse(request, "index.html", {"request": request})
