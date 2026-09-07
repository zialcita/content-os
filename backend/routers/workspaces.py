from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from models.entities import User, Workspace
from schemas import WorkspaceCreate, WorkspaceOut
from services.auth import generate_api_key, get_workspace, hash_api_key
from services.audit import log_event

router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceOut)
def create_workspace(body: WorkspaceCreate, db: Session = Depends(get_db)) -> WorkspaceOut:
    raw_key = generate_api_key()
    workspace = Workspace(
        name=body.name,
        api_key_hash=hash_api_key(raw_key),
        api_key_prefix=raw_key[:12],
        spend_limit_usd=get_settings().spend_limit_usd,
    )
    db.add(workspace)
    db.flush()
    db.add(
        User(
            workspace_id=workspace.id,
            email=body.owner_email,
            name=body.owner_name,
            role="owner",
        )
    )
    log_event(db, workspace.id, "workspace.created", actor=body.owner_email, entity_type="workspace", entity_id=workspace.id)
    db.commit()
    db.refresh(workspace)
    out = WorkspaceOut.model_validate(workspace)
    return out.model_copy(update={"api_key": raw_key})


@router.get("/me", response_model=WorkspaceOut)
def me(workspace: Workspace = Depends(get_workspace)) -> Workspace:
    return workspace
