from typing import Any

from sqlalchemy.orm import Session

from models.entities import AuditLog


def log_event(
    db: Session,
    workspace_id: str,
    action: str,
    *,
    actor: str = "system",
    entity_type: str = "",
    entity_id: str = "",
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(
        workspace_id=workspace_id,
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
    )
    db.add(row)
    return row
