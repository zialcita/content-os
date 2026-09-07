from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from adapters.assembly import get_assembly_engine
from adapters.avatar import get_avatar_engine
from adapters.broll import get_broll_engine
from adapters.clip import get_clip_engine
from adapters.youtube import get_youtube_adapter
from models.entities import (
    Clip,
    MediaAsset,
    Persona,
    RenderJob,
    VideoProject,
    VideoScene,
    Workspace,
)
from models.enums import FORWARD, AssetKind, AssetSource, JobStatus, JobType, VideoStatus
from services.audit import log_event
from services.llm import generate_script
from services.spend import record_spend


def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_scenes(script: str) -> list[tuple[str, str]]:
    chunks = re.split(r"(?m)^##\s+", script)
    scenes: list[tuple[str, str]] = []
    for chunk in chunks[1:] if len(chunks) > 1 else [script]:
        lines = [ln.strip() for ln in chunk.strip().splitlines() if ln.strip()]
        spoken: list[str] = []
        visual = ""
        for line in lines:
            upper = line.upper()
            if upper.startswith("SCRIPT:"):
                spoken.append(line.split(":", 1)[1].strip())
            elif upper.startswith("BROLL:") or upper.startswith("VISUAL:"):
                visual = line.split(":", 1)[1].strip()
            elif not line.startswith("#"):
                spoken.append(line)
        text = " ".join(spoken).strip() or chunk.strip()
        scenes.append((text, visual))
    if not scenes:
        scenes.append((script.strip() or "Untitled scene", "talking head"))
    return scenes[:12]


def transition(video: VideoProject, dest: VideoStatus) -> None:
    current = VideoStatus(video.status)
    if dest == current:
        return
    allowed = FORWARD.get(current, ())
    if dest not in allowed and dest != VideoStatus.FAILED:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot move from {current.value} to {dest.value}",
        )
    video.status = dest.value
    video.updated_at = _now()


def replace_scenes(db: Session, video: VideoProject, script: str) -> None:
    db.query(VideoScene).filter(VideoScene.video_id == video.id).delete()
    for idx, (text, visual) in enumerate(parse_scenes(script)):
        db.add(
            VideoScene(
                video_id=video.id,
                idx=idx,
                script_text=text,
                visual_direction=visual,
            )
        )


def _job(
    db: Session,
    workspace: Workspace,
    video: VideoProject,
    job_type: JobType,
    provider: str,
    status: JobStatus = JobStatus.QUEUED,
) -> RenderJob:
    job = RenderJob(
        workspace_id=workspace.id,
        video_id=video.id,
        job_type=job_type.value,
        provider=provider,
        status=status.value,
    )
    db.add(job)
    db.flush()
    return job


def _finish_job(job: RenderJob, *, ok: bool, payload: dict, error: str = "", external_id: str = "") -> None:
    job.status = JobStatus.COMPLETED.value if ok else JobStatus.FAILED.value
    job.result_payload = payload
    job.error = error
    job.external_id = external_id
    job.updated_at = _now()


def create_video(
    db: Session,
    workspace: Workspace,
    *,
    title: str,
    topic: str = "",
    brand_id: str | None = None,
    persona_id: str | None = None,
    avatar_id: str | None = None,
) -> VideoProject:
    video = VideoProject(
        workspace_id=workspace.id,
        brand_id=brand_id,
        persona_id=persona_id,
        avatar_id=avatar_id,
        title=title,
        topic=topic,
        status=VideoStatus.SCRIPTING.value,
    )
    db.add(video)
    db.flush()

    tone = ""
    if persona_id:
        persona = db.get(Persona, persona_id)
        if persona and persona.workspace_id == workspace.id:
            tone = persona.tone

    job = _job(db, workspace, video, JobType.SCRIPT, "llm", JobStatus.RUNNING)
    result = generate_script(title=title, topic=topic, persona_tone=tone)
    record_spend(
        db,
        workspace,
        provider=result.provider,
        operation="script.generate",
        amount_usd=result.cost_usd,
        video_id=video.id,
    )
    script = str(result.payload.get("script") or "")
    video.script_draft = script
    replace_scenes(db, video, script)
    _finish_job(job, ok=result.ok, payload=result.payload, error=result.error)
    if result.ok:
        transition(video, VideoStatus.SCRIPT_READY)
    else:
        transition(video, VideoStatus.FAILED)
        video.error = result.error
    log_event(
        db,
        workspace.id,
        "video.created",
        entity_type="video_project",
        entity_id=video.id,
        payload={"title": title, "status": video.status},
    )
    db.commit()
    db.refresh(video)
    return video


def edit_script(db: Session, workspace: Workspace, video: VideoProject, script: str) -> VideoProject:
    if video.status not in {VideoStatus.SCRIPT_READY.value, VideoStatus.SCRIPTING.value}:
        raise HTTPException(status_code=409, detail="Script can only be edited before approval")
    video.script_draft = script
    replace_scenes(db, video, script)
    video.status = VideoStatus.SCRIPT_READY.value
    video.updated_at = _now()
    log_event(
        db,
        workspace.id,
        "video.script_edited",
        entity_type="video_project",
        entity_id=video.id,
    )
    db.commit()
    db.refresh(video)
    return video


def approve_script(db: Session, workspace: Workspace, video: VideoProject) -> VideoProject:
    if video.status != VideoStatus.SCRIPT_READY.value:
        raise HTTPException(status_code=409, detail="Video is not awaiting script approval")
    video.script_final = video.script_draft
    transition(video, VideoStatus.SCRIPT_APPROVED)
    log_event(
        db,
        workspace.id,
        "video.script_approved",
        actor="human",
        entity_type="video_project",
        entity_id=video.id,
    )
    render_avatar(db, workspace, video, commit=False)
    db.commit()
    db.refresh(video)
    return video


def render_avatar(
    db: Session,
    workspace: Workspace,
    video: VideoProject,
    *,
    commit: bool = True,
) -> VideoProject:
    if video.status == VideoStatus.SCRIPT_APPROVED.value:
        transition(video, VideoStatus.RENDERING_AVATAR)
    elif video.status != VideoStatus.RENDERING_AVATAR.value:
        raise HTTPException(status_code=409, detail="Avatar render not allowed in this status")

    engine = get_avatar_engine()
    job = _job(
        db,
        workspace,
        video,
        JobType.AVATAR,
        "heygen" if engine.is_configured() else "simulated",
        JobStatus.RUNNING,
    )
    result = engine.render(
        script=video.script_final or video.script_draft,
        avatar_id=video.avatar_id or "",
        title=video.title,
    )
    record_spend(
        db,
        workspace,
        provider=result.provider,
        operation="avatar.render",
        amount_usd=result.cost_usd,
        video_id=video.id,
    )
    _finish_job(job, ok=result.ok, payload=result.payload, error=result.error, external_id=result.external_id)
    if not result.ok:
        transition(video, VideoStatus.FAILED)
        video.error = result.error
    else:
        asset = MediaAsset(
            workspace_id=workspace.id,
            kind=AssetKind.AROLL.value,
            source=AssetSource.HEYGEN.value if result.provider == "heygen" else AssetSource.SIMULATED.value,
            uri=result.uri,
            title=f"{video.title} A-roll",
            extra=result.payload,
        )
        db.add(asset)
        db.flush()
        scenes = (
            db.query(VideoScene)
            .filter(VideoScene.video_id == video.id)
            .order_by(VideoScene.idx)
            .all()
        )
        if scenes:
            scenes[0].aroll_asset_id = asset.id
        transition(video, VideoStatus.AVATAR_READY)
    if commit:
        db.commit()
        db.refresh(video)
    return video


def resolve_broll(db: Session, workspace: Workspace, video: VideoProject) -> VideoProject:
    if video.status != VideoStatus.AVATAR_READY.value:
        raise HTTPException(status_code=409, detail="B-roll resolve requires avatar_ready")
    transition(video, VideoStatus.RESOLVING_BROLL)
    engine = get_broll_engine()
    scenes = (
        db.query(VideoScene).filter(VideoScene.video_id == video.id).order_by(VideoScene.idx).all()
    )
    job = _job(db, workspace, video, JobType.BROLL, "waterfall", JobStatus.RUNNING)
    payloads: list[dict] = []
    for scene in scenes:
        query = scene.visual_direction or scene.script_text[:80]
        result = engine.resolve(db, workspace.id, query=query)
        record_spend(
            db,
            workspace,
            provider=result.provider,
            operation="broll.resolve",
            amount_usd=result.cost_usd,
            video_id=video.id,
        )
        if result.payload.get("asset_id"):
            scene.broll_asset_id = str(result.payload["asset_id"])
        else:
            source = {
                "library": AssetSource.LIBRARY,
                "pexels": AssetSource.PEXELS,
                "higgsfield": AssetSource.HIGGSFIELD,
            }.get(result.provider, AssetSource.SIMULATED)
            asset = MediaAsset(
                workspace_id=workspace.id,
                kind=AssetKind.BROLL.value,
                source=source.value,
                uri=result.uri,
                title=query[:200],
                extra=result.payload,
            )
            db.add(asset)
            db.flush()
            scene.broll_asset_id = asset.id
        payloads.append({"scene": scene.idx, **result.payload, "uri": result.uri, "provider": result.provider})
    _finish_job(job, ok=True, payload={"scenes": payloads})
    db.commit()
    db.refresh(video)
    return video


def assemble(db: Session, workspace: Workspace, video: VideoProject) -> VideoProject:
    if video.status != VideoStatus.RESOLVING_BROLL.value:
        raise HTTPException(status_code=409, detail="Assemble requires resolving_broll")
    transition(video, VideoStatus.ASSEMBLING)
    scenes = (
        db.query(VideoScene).filter(VideoScene.video_id == video.id).order_by(VideoScene.idx).all()
    )
    uris: list[str] = []
    for scene in scenes:
        if scene.aroll_asset_id:
            asset = db.get(MediaAsset, scene.aroll_asset_id)
            if asset:
                uris.append(asset.uri)
        if scene.broll_asset_id:
            asset = db.get(MediaAsset, scene.broll_asset_id)
            if asset:
                uris.append(asset.uri)
    engine = get_assembly_engine()
    job = _job(
        db,
        workspace,
        video,
        JobType.ASSEMBLY,
        "shotstack" if engine.is_configured() else "simulated",
        JobStatus.RUNNING,
    )
    result = engine.assemble(title=video.title, scene_uris=uris)
    record_spend(
        db,
        workspace,
        provider=result.provider,
        operation="assembly.render",
        amount_usd=result.cost_usd,
        video_id=video.id,
    )
    _finish_job(job, ok=result.ok, payload=result.payload, error=result.error, external_id=result.external_id)
    if not result.ok:
        transition(video, VideoStatus.FAILED)
        video.error = result.error
    else:
        db.add(
            MediaAsset(
                workspace_id=workspace.id,
                kind=AssetKind.ASSEMBLY.value,
                source=AssetSource.SHOTSTACK.value if result.provider == "shotstack" else AssetSource.SIMULATED.value,
                uri=result.uri,
                title=f"{video.title} final cut",
                extra=result.payload,
            )
        )
        transition(video, VideoStatus.ASSEMBLY_READY)
        transition(video, VideoStatus.IN_REVIEW)
    db.commit()
    db.refresh(video)
    return video


def approve_cut(db: Session, workspace: Workspace, video: VideoProject) -> VideoProject:
    if video.status != VideoStatus.IN_REVIEW.value:
        raise HTTPException(status_code=409, detail="Final-cut approval requires in_review")
    transition(video, VideoStatus.APPROVED)
    log_event(
        db,
        workspace.id,
        "video.cut_approved",
        actor="human",
        entity_type="video_project",
        entity_id=video.id,
    )
    db.commit()
    db.refresh(video)
    return video


def generate_clips(db: Session, workspace: Workspace, video: VideoProject) -> list[Clip]:
    engine = get_clip_engine()
    job = _job(db, workspace, video, JobType.CLIP, "simulated", JobStatus.RUNNING)
    results = engine.cut(title=video.title)
    clips: list[Clip] = []
    for result in results:
        asset = MediaAsset(
            workspace_id=workspace.id,
            kind=AssetKind.CLIP.value,
            source=AssetSource.SIMULATED.value,
            uri=result.uri,
            title=str(result.payload.get("title") or video.title),
            extra=result.payload,
        )
        db.add(asset)
        db.flush()
        clip = Clip(
            workspace_id=workspace.id,
            video_id=video.id,
            asset_id=asset.id,
            title=asset.title,
            start_s=float(result.payload.get("start_s") or 0),
            end_s=float(result.payload.get("end_s") or 0),
        )
        db.add(clip)
        clips.append(clip)
    _finish_job(job, ok=True, payload={"count": len(clips)})
    return clips


def publish(db: Session, workspace: Workspace, video: VideoProject) -> VideoProject:
    if video.status != VideoStatus.APPROVED.value:
        raise HTTPException(status_code=409, detail="Publish requires approved")
    transition(video, VideoStatus.PUBLISHING)
    assembly = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.workspace_id == workspace.id,
            MediaAsset.kind == AssetKind.ASSEMBLY.value,
        )
        .order_by(MediaAsset.created_at.desc())
        .first()
    )
    adapter = get_youtube_adapter()
    job = _job(
        db,
        workspace,
        video,
        JobType.PUBLISH,
        "youtube" if adapter.is_configured() else "simulated",
        JobStatus.RUNNING,
    )
    result = adapter.publish(title=video.title, uri=assembly.uri if assembly else "")
    _finish_job(job, ok=result.ok, payload=result.payload, error=result.error, external_id=result.external_id)
    if not result.ok:
        transition(video, VideoStatus.FAILED)
        video.error = result.error
    else:
        video.youtube_video_id = result.external_id
        video.published_url = result.uri
        generate_clips(db, workspace, video)
        transition(video, VideoStatus.PUBLISHED)
        log_event(
            db,
            workspace.id,
            "video.published",
            entity_type="video_project",
            entity_id=video.id,
            payload={"url": video.published_url},
        )
    db.commit()
    db.refresh(video)
    return video


def get_owned_video(db: Session, workspace: Workspace, video_id: str) -> VideoProject:
    video = db.get(VideoProject, video_id)
    if not video or video.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Video not found")
    return video
