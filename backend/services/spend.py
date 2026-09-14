import math
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from config import get_settings
from models.entities import CostLedger, Workspace
from services.runtime_policy import RuntimeSafetyError, require_legacy_simulation


class SpendLimitExceeded(HTTPException):
    def __init__(self, current: float, attempted: float, limit: float) -> None:
        super().__init__(
            status_code=402,
            detail={
                "error": "spend_limit_exceeded",  # Preserve legacy client compatibility.
                "code": "BUDGET_EXCEEDED",
                "message": "Simulation usage exceeds the configured fixture budget.",
                "field_errors": [],
                "retryable": False,
                "correlation_id": str(uuid4()),
                "usage_kind": "simulation_not_provider_spend",
                "current_usd": current,
                "attempted_usd": attempted,
                "limit_usd": limit,
            },
        )


def assert_can_spend(workspace: Workspace, amount_usd: float) -> None:
    settings = get_settings()
    require_legacy_simulation(settings)
    # Only missing values inherit configuration. Zero is always a hard zero.
    limit = settings.spend_limit_usd if workspace.spend_limit_usd is None else workspace.spend_limit_usd
    if any(not math.isfinite(value) or value < 0 for value in (workspace.spend_usd, amount_usd, limit)):
        raise RuntimeSafetyError("INVALID_BUDGET", "Budget and usage values must be finite and nonnegative.")
    if workspace.spend_usd + amount_usd > limit:
        raise SpendLimitExceeded(workspace.spend_usd, amount_usd, limit)


def record_spend(
    db: Session,
    workspace: Workspace,
    *,
    provider: str,
    operation: str,
    amount_usd: float,
    video_id: str | None = None,
) -> CostLedger:
    assert_can_spend(workspace, amount_usd)
    if provider != "simulated" and not (provider == "library" and amount_usd == 0):
        raise RuntimeSafetyError("LIVE_SPEND_DISABLED", "Legacy accounting accepts simulation fixtures only.")
    # Compatibility counters remain fixture units, NOT settled provider spend.
    # Fixed-precision atomic reservations live in the separately owned v6 ledger.
    entry = CostLedger(
        workspace_id=workspace.id,
        video_id=video_id,
        provider="simulated",
        operation=f"simulation.{operation}",
        amount_usd=amount_usd,
    )
    workspace.spend_usd = round(workspace.spend_usd + amount_usd, 6)
    db.add(entry)
    db.add(workspace)
    return entry
