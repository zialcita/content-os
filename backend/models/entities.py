from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    api_key_prefix: Mapped[str] = mapped_column(String(16))
    spend_usd: Mapped[float] = mapped_column(Float, default=0.0)
    spend_limit_usd: Mapped[float] = mapped_column(Float, default=25.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    users: Mapped[list[User]] = relationship(back_populates="workspace")
    brands: Mapped[list[Brand]] = relationship(back_populates="workspace")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(32), default="owner")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    workspace: Mapped[Workspace] = relationship(back_populates="users")

    __table_args__ = (UniqueConstraint("workspace_id", "email", name="uq_user_ws_email"),)


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    voice: Mapped[str] = mapped_column(Text, default="")
    guidelines: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    workspace: Mapped[Workspace] = relationship(back_populates="brands")
    personas: Mapped[list[Persona]] = relationship(back_populates="brand")


class Persona(Base):
    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    brand_id: Mapped[str | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    tone: Mapped[str] = mapped_column(String(200), default="")
    audience: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    brand: Mapped[Brand | None] = relationship(back_populates="personas")


class ResearchSource(Base):
    __tablename__ = "research_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(2000), default="")
    source_type: Mapped[str] = mapped_column(String(64), default="web")
    status: Mapped[str] = mapped_column(String(32), default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    evidence: Mapped[list[EvidenceItem]] = relationship(back_populates="source")


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("research_sources.id"), index=True)
    title: Mapped[str] = mapped_column(String(400))
    content: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(2000), default="")
    # JSON array now; pgvector extension is enabled on Postgres for later Vector(1536) swap.
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    source: Mapped[ResearchSource] = relationship(back_populates="evidence")


class AvatarProfile(Base):
    __tablename__ = "avatar_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    provider: Mapped[str] = mapped_column(String(32), default="simulated")
    provider_avatar_id: Mapped[str] = mapped_column(String(200), default="")
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class VideoProject(Base):
    __tablename__ = "video_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    brand_id: Mapped[str | None] = mapped_column(ForeignKey("brands.id"), nullable=True)
    persona_id: Mapped[str | None] = mapped_column(ForeignKey("personas.id"), nullable=True)
    avatar_id: Mapped[str | None] = mapped_column(ForeignKey("avatar_profiles.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    topic: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="scripting", index=True)
    script_draft: Mapped[str] = mapped_column(Text, default="")
    script_final: Mapped[str] = mapped_column(Text, default="")
    youtube_video_id: Mapped[str] = mapped_column(String(64), default="")
    published_url: Mapped[str] = mapped_column(String(2000), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    scenes: Mapped[list[VideoScene]] = relationship(
        back_populates="video", order_by="VideoScene.idx", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[RenderJob]] = relationship(back_populates="video")
    clips: Mapped[list[Clip]] = relationship(back_populates="video")


class VideoScene(Base):
    __tablename__ = "video_scenes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    video_id: Mapped[str] = mapped_column(ForeignKey("video_projects.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    script_text: Mapped[str] = mapped_column(Text, default="")
    visual_direction: Mapped[str] = mapped_column(Text, default="")
    aroll_asset_id: Mapped[str | None] = mapped_column(ForeignKey("media_assets.id"), nullable=True)
    broll_asset_id: Mapped[str | None] = mapped_column(ForeignKey("media_assets.id"), nullable=True)

    video: Mapped[VideoProject] = relationship(back_populates="scenes")


class RenderJob(Base):
    __tablename__ = "render_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    video_id: Mapped[str | None] = mapped_column(ForeignKey("video_projects.id"), nullable=True)
    job_type: Mapped[str] = mapped_column(String(32), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="simulated")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    external_id: Mapped[str] = mapped_column(String(200), default="")
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    video: Mapped[VideoProject | None] = relationship(back_populates="jobs")


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="other")
    source: Mapped[str] = mapped_column(String(32), default="simulated")
    uri: Mapped[str] = mapped_column(String(2000))
    title: Mapped[str] = mapped_column(String(300), default="")
    extra: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("video_projects.id"), index=True)
    asset_id: Mapped[str | None] = mapped_column(ForeignKey("media_assets.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300), default="")
    start_s: Mapped[float] = mapped_column(Float, default=0.0)
    end_s: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    video: Mapped[VideoProject] = relationship(back_populates="clips")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[str] = mapped_column(String(36), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CostLedger(Base):
    __tablename__ = "cost_ledger"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    video_id: Mapped[str | None] = mapped_column(ForeignKey("video_projects.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(32))
    operation: Mapped[str] = mapped_column(String(80))
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
