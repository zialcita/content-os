from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from adapters.storage import get_storage
from database import get_db
from models.entities import MediaAsset, Workspace
from schemas import AssetIn, AssetOut
from services.auth import get_workspace

router = APIRouter(prefix="/v1/assets", tags=["assets"])


@router.post("", response_model=AssetOut)
def create_asset(
    body: AssetIn,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> MediaAsset:
    uri = body.uri
    if not uri:
        stored = get_storage().put_bytes(
            f"{workspace.id}/library/{body.title.replace(' ', '-').lower()}.txt",
            f"library placeholder for {body.title}".encode(),
            "text/plain",
        )
        uri = stored.uri
    asset = MediaAsset(
        workspace_id=workspace.id,
        kind=body.kind,
        source=body.source,
        uri=uri,
        title=body.title,
        extra=body.extra,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get("", response_model=list[AssetOut])
def list_assets(
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> list[MediaAsset]:
    return (
        db.query(MediaAsset)
        .filter(MediaAsset.workspace_id == workspace.id)
        .order_by(MediaAsset.created_at.desc())
        .all()
    )
