from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.entities import Persona, Workspace
from schemas import PersonaIn, PersonaOut
from services.auth import get_workspace

router = APIRouter(prefix="/v1/personas", tags=["personas"])


@router.post("", response_model=PersonaOut)
def create_persona(
    body: PersonaIn,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> Persona:
    persona = Persona(workspace_id=workspace.id, **body.model_dump())
    db.add(persona)
    db.commit()
    db.refresh(persona)
    return persona


@router.get("", response_model=list[PersonaOut])
def list_personas(
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> list[Persona]:
    return db.query(Persona).filter(Persona.workspace_id == workspace.id).all()


@router.get("/{persona_id}", response_model=PersonaOut)
def get_persona(
    persona_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> Persona:
    persona = db.get(Persona, persona_id)
    if not persona or persona.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona
