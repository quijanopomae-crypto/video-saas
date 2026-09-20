from fastapi import APIRouter, HTTPException

from ...core.config import get_settings
from ...core.db import database_is_ready

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "video-saas-api",
        "environment": settings.app_env,
        "adapters": {
            "storage": settings.storage_backend,
            "queue": settings.queue_backend,
            "workflow": settings.workflow_backend,
        },
    }


@router.get("/ready")
def ready() -> dict[str, str]:
    try:
        ok = database_is_ready()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    if not ok:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ready", "database": "ok"}
