from fastapi import HTTPException
from sqlalchemy.orm import Session

from config import get_settings
from models.entities import CostLedger, Workspace


class SpendLimitExceeded(HTTPException):
    def __init__(self, current: float, attempted: float, limit: float) -> None:
        super().__init__(
            status_code=402,
            detail={
                "error": "spend_limit_exceeded",
                "current_usd": current,
                "attempted_usd": attempted,
                "limit_usd": limit,
            },
        )


def assert_can_spend(workspace: Workspace, amount_usd: float) -> None:
    limit = workspace.spend_limit_usd or get_settings().spend_limit_usd
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
    entry = CostLedger(
        workspace_id=workspace.id,
        video_id=video_id,
        provider=provider,
        operation=operation,
        amount_usd=amount_usd,
    )
    workspace.spend_usd = round(workspace.spend_usd + amount_usd, 6)
    db.add(entry)
    db.add(workspace)
    return entry
