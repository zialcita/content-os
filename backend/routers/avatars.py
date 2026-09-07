from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.entities import AvatarProfile, Workspace
from schemas import AvatarIn, AvatarOut
from services.auth import get_workspace

router = APIRouter(prefix="/v1/avatars", tags=["avatars"])


@router.post("", response_model=AvatarOut)
def create_avatar(
    body: AvatarIn,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> AvatarProfile:
    avatar = AvatarProfile(workspace_id=workspace.id, **body.model_dump())
    db.add(avatar)
    db.commit()
    db.refresh(avatar)
    return avatar


@router.get("", response_model=list[AvatarOut])
def list_avatars(
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> list[AvatarProfile]:
    return db.query(AvatarProfile).filter(AvatarProfile.workspace_id == workspace.id).all()


@router.get("/{avatar_id}", response_model=AvatarOut)
def get_avatar(
    avatar_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> AvatarProfile:
    avatar = db.get(AvatarProfile, avatar_id)
    if not avatar or avatar.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Avatar not found")
    return avatar
