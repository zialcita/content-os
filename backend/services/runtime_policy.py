"""Fail-closed boundary for the legacy API; not a production-readiness switch."""

from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import HTTPException

if TYPE_CHECKING:
    from config import Settings


class RuntimeSafetyError(HTTPException):
    """Typed startup/request refusal without disclosing configuration secrets."""

    def __init__(self, code: str, message: str, *, status_code: int = 503) -> None:
        self.code = code
        super().__init__(
            status_code=status_code,
            detail={
                "code": code,
                "message": message,
                "field_errors": [],
                "retryable": False,
                "correlation_id": str(uuid4()),
            },
        )


def require_legacy_simulation(settings: "Settings") -> None:
    # Exact allowlist: typos, staging, PROD, whitespace, etc. cannot enter a
    # permissive non-production branch. No environment variable unlocks live use.
    if settings.app_env not in {"development", "test", "production"}:
        raise RuntimeSafetyError("UNSUPPORTED_ENVIRONMENT", "APP_ENV must be development, test or production.")
    if settings.app_env == "production":
        raise RuntimeSafetyError(
            "LEGACY_PRODUCTION_DISABLED",
            "Legacy production startup is disabled: v6 secure migrations, OIDC/session authorization, "
            "durable workers and atomic budget integration are not wired into this application.",
        )
    if settings.runtime_mode != "simulation":
        raise RuntimeSafetyError(
            "SIMULATION_OPT_IN_REQUIRED",
            "Legacy development/test use requires explicit RUNTIME_MODE=simulation; no provider fallback is allowed.",
        )
    if (
        settings.avatar_engine != "simulated"
        or settings.broll_engine != "simulated"
        or settings.assembly_engine != "simulated"
        or settings.storage_backend != "local"
    ):
        raise RuntimeSafetyError(
            "LIVE_CONFIGURATION_FORBIDDEN",
            "Legacy simulation requires simulated engines and local storage; live adapters are not implemented.",
        )
    # Several legacy stubs choose a provider solely from credential presence,
    # ignoring engine selection. Reject rather than clear or silently fall back.
    credential_fields = (
        "ai_api_key", "heygen_api_key", "pexels_api_key", "higgsfield_api_key",
        "shotstack_api_key", "s3_access_key_id", "s3_secret_access_key",
        "google_client_id", "google_client_secret", "youtube_refresh_token", "youtube_channel_id",
    )
    if any(getattr(settings, field) for field in credential_fields):
        raise RuntimeSafetyError(
            "LIVE_CONFIGURATION_FORBIDDEN",
            "Remove provider/account credentials from the isolated legacy simulation environment.",
        )
