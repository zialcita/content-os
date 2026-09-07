from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    owner_email: str = "owner@example.com"
    owner_name: str = "Owner"


class WorkspaceOut(BaseModel):
    id: str
    name: str
    api_key_prefix: str
    spend_usd: float
    spend_limit_usd: float
    created_at: datetime | None = None
    api_key: str | None = None

    model_config = {"from_attributes": True}


class BrandIn(BaseModel):
    name: str
    voice: str = ""
    guidelines: str = ""


class BrandOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    voice: str
    guidelines: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class PersonaIn(BaseModel):
    name: str
    brand_id: str | None = None
    description: str = ""
    tone: str = ""
    audience: str = ""


class PersonaOut(BaseModel):
    id: str
    workspace_id: str
    brand_id: str | None
    name: str
    description: str
    tone: str
    audience: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SourceIn(BaseModel):
    name: str
    url: str = ""
    source_type: str = "web"


class SourceOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    url: str
    source_type: str
    status: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class EvidenceIn(BaseModel):
    title: str
    content: str = ""
    url: str = ""


class EvidenceOut(BaseModel):
    id: str
    workspace_id: str
    source_id: str
    title: str
    content: str
    url: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AvatarIn(BaseModel):
    name: str
    provider: str = "simulated"
    provider_avatar_id: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)


class AvatarOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    provider: str
    provider_avatar_id: str
    settings: dict[str, Any]
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class AssetIn(BaseModel):
    title: str
    kind: str = "broll"
    uri: str = ""
    source: str = "library"
    extra: dict[str, Any] = Field(default_factory=dict)


class AssetOut(BaseModel):
    id: str
    workspace_id: str
    kind: str
    source: str
    uri: str
    title: str
    extra: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SceneOut(BaseModel):
    id: str
    idx: int
    script_text: str
    visual_direction: str
    aroll_asset_id: str | None
    broll_asset_id: str | None

    model_config = {"from_attributes": True}


class VideoCreate(BaseModel):
    title: str
    topic: str = ""
    brand_id: str | None = None
    persona_id: str | None = None
    avatar_id: str | None = None


class ScriptEdit(BaseModel):
    script: str
    scenes: list[dict[str, Any]] | None = None


class VideoOut(BaseModel):
    id: str
    workspace_id: str
    brand_id: str | None
    persona_id: str | None
    avatar_id: str | None
    title: str
    topic: str
    status: str
    script_draft: str
    script_final: str
    youtube_video_id: str
    published_url: str
    error: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    scenes: list[SceneOut] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ClipOut(BaseModel):
    id: str
    video_id: str
    asset_id: str | None
    title: str
    start_s: float
    end_s: float
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: str
    video_id: str | None
    job_type: str
    provider: str
    status: str
    external_id: str
    result_payload: dict[str, Any]
    error: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
