from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import get_db
from models.entities import EvidenceItem, ResearchSource, Workspace
from schemas import EvidenceIn, EvidenceOut, SourceIn, SourceOut
from services.auth import get_workspace

router = APIRouter(tags=["sources"])


@router.post("/v1/sources", response_model=SourceOut)
def create_source(
    body: SourceIn,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> ResearchSource:
    source = ResearchSource(workspace_id=workspace.id, **body.model_dump())
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


@router.get("/v1/sources", response_model=list[SourceOut])
def list_sources(
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> list[ResearchSource]:
    return db.query(ResearchSource).filter(ResearchSource.workspace_id == workspace.id).all()


@router.get("/v1/sources/{source_id}", response_model=SourceOut)
def get_source(
    source_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> ResearchSource:
    source = db.get(ResearchSource, source_id)
    if not source or source.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.post("/v1/sources/{source_id}/evidence", response_model=EvidenceOut)
def add_evidence(
    source_id: str,
    body: EvidenceIn,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> EvidenceItem:
    source = db.get(ResearchSource, source_id)
    if not source or source.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Source not found")
    item = EvidenceItem(workspace_id=workspace.id, source_id=source.id, **body.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/v1/evidence/search", response_model=list[EvidenceOut])
def search_evidence(
    q: str = Query(min_length=1),
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> list[EvidenceItem]:
    like = f"%{q}%"
    return (
        db.query(EvidenceItem)
        .filter(
            EvidenceItem.workspace_id == workspace.id,
            or_(EvidenceItem.title.ilike(like), EvidenceItem.content.ilike(like)),
        )
        .limit(50)
        .all()
    )
