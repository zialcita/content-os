from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, selectinload

from database import get_db
from models.entities import Clip, VideoProject, Workspace
from schemas import ClipOut, JobOut, ScriptEdit, VideoCreate, VideoOut
from services.auth import get_workspace
from services.pipeline import (
    approve_cut,
    approve_script,
    assemble,
    create_video,
    edit_script,
    generate_clips,
    get_owned_video,
    publish,
    resolve_broll,
)
router = APIRouter(prefix="/v1/videos", tags=["videos"])


def _load(db: Session, video: VideoProject) -> VideoProject:
    return (
        db.query(VideoProject)
        .options(selectinload(VideoProject.scenes))
        .filter(VideoProject.id == video.id)
        .one()
    )


@router.post("", response_model=VideoOut)
def create(
    body: VideoCreate,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> VideoProject:
    video = create_video(db, workspace, **body.model_dump())
    return _load(db, video)


@router.get("", response_model=list[VideoOut])
def list_videos(
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> list[VideoProject]:
    return (
        db.query(VideoProject)
        .options(selectinload(VideoProject.scenes))
        .filter(VideoProject.workspace_id == workspace.id)
        .order_by(VideoProject.created_at.desc())
        .all()
    )


@router.get("/{video_id}", response_model=VideoOut)
def get_video(
    video_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> VideoProject:
    return _load(db, get_owned_video(db, workspace, video_id))


@router.patch("/{video_id}/script", response_model=VideoOut)
def edit(
    video_id: str,
    body: ScriptEdit,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> VideoProject:
    video = get_owned_video(db, workspace, video_id)
    return _load(db, edit_script(db, workspace, video, body.script))


@router.post("/{video_id}/approve-script", response_model=VideoOut)
def approve_script_endpoint(
    video_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> VideoProject:
    video = get_owned_video(db, workspace, video_id)
    return _load(db, approve_script(db, workspace, video))


@router.post("/{video_id}/resolve-broll", response_model=VideoOut)
def resolve_broll_endpoint(
    video_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> VideoProject:
    video = get_owned_video(db, workspace, video_id)
    return _load(db, resolve_broll(db, workspace, video))


@router.post("/{video_id}/assemble", response_model=VideoOut)
def assemble_endpoint(
    video_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> VideoProject:
    video = get_owned_video(db, workspace, video_id)
    return _load(db, assemble(db, workspace, video))


@router.post("/{video_id}/approve", response_model=VideoOut)
def approve_cut_endpoint(
    video_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> VideoProject:
    video = get_owned_video(db, workspace, video_id)
    return _load(db, approve_cut(db, workspace, video))


@router.post("/{video_id}/publish", response_model=VideoOut)
def publish_endpoint(
    video_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> VideoProject:
    video = get_owned_video(db, workspace, video_id)
    return _load(db, publish(db, workspace, video))


@router.get("/{video_id}/clips", response_model=list[ClipOut])
def list_clips(
    video_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> list[Clip]:
    video = get_owned_video(db, workspace, video_id)
    return db.query(Clip).filter(Clip.video_id == video.id).all()


@router.post("/{video_id}/clips", response_model=list[ClipOut])
def make_clips(
    video_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
) -> list[Clip]:
    video = get_owned_video(db, workspace, video_id)
    clips = generate_clips(db, workspace, video)
    db.commit()
    return clips


@router.get("/{video_id}/jobs", response_model=list[JobOut])
def list_jobs(
    video_id: str,
    db: Session = Depends(get_db),
    workspace: Workspace = Depends(get_workspace),
):
    video = get_owned_video(db, workspace, video_id)
    return video.jobs
