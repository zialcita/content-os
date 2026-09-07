from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.entities import Brand, Workspace
from schemas import BrandIn, BrandOut
from services.auth import get_workspace

router = APIRouter(prefix="/v1/brands", tags=["brands"])


@router.post("", response_model=BrandOut)
def create_brand(
    body: BrandIn,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> Brand:
    brand = Brand(workspace_id=workspace.id, **body.model_dump())
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


@router.get("", response_model=list[BrandOut])
def list_brands(
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> list[Brand]:
    return db.query(Brand).filter(Brand.workspace_id == workspace.id).all()


@router.get("/{brand_id}", response_model=BrandOut)
def get_brand(
    brand_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> Brand:
    brand = db.get(Brand, brand_id)
    if not brand or brand.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Brand not found")
    return brand
