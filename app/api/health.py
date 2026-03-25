from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("", include_in_schema=True)
@router.get("/", include_in_schema=False)
def health_check():
    """Lightweight liveness probe for dev / orchestration (no DB or disk checks)."""
    return {"status": "healthy", "app_env": settings.app_env}
