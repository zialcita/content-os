import hashlib
import secrets

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.entities import Workspace


def generate_api_key() -> str:
    return f"cos_{secrets.token_urlsafe(32)}"


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_workspace(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> Workspace:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key")
    workspace = (
        db.query(Workspace).filter(Workspace.api_key_hash == hash_api_key(x_api_key)).first()
    )
    if not workspace:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return workspace
