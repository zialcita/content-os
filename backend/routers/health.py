from fastapi import APIRouter, Depends

from config import get_settings
from models.entities import Workspace
from services.auth import get_workspace
from services.scheduler import tick_once

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/v1/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "env": settings.app_env,
        "engines": {
            "avatar": settings.avatar_engine,
            "broll": settings.broll_engine,
            "assembly": settings.assembly_engine,
            "storage": settings.storage_backend,
        },
    }


@router.post("/v1/jobs/tick")
def tick_jobs(_: Workspace = Depends(get_workspace)) -> dict:
    return {"advanced": tick_once()}
