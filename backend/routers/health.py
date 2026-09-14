from fastapi import APIRouter

from config import get_settings
from services.runtime_policy import RuntimeSafetyError, require_legacy_simulation

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/v1/health")
def health() -> dict:
    settings = get_settings()
    require_legacy_simulation(settings)
    return {
        "status": "ok",
        "env": settings.app_env,
        "runtime_mode": "simulation",
        "production_ready": False,
        "usage_kind": "simulation_not_provider_spend",
        "publication_kind": "simulation_not_live",
        "global_tick_enabled": False,
        "engines": {
            "avatar": settings.avatar_engine,
            "broll": settings.broll_engine,
            "assembly": settings.assembly_engine,
            "storage": settings.storage_backend,
        },
    }


@router.post("/v1/jobs/tick")
def tick_jobs() -> dict:
    # No database/auth dependency and no scheduler import. A workspace key can
    # never authorize cross-workspace operational work, in any API mode.
    raise RuntimeSafetyError(
        "GLOBAL_TICK_DISABLED",
        "Legacy global job advancement is disabled; use the future authorized durable worker service.",
    )
