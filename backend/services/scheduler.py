import asyncio
import logging
from datetime import datetime, timezone

from config import get_settings
from database import SessionLocal
from models.entities import RenderJob, VideoProject, Workspace
from models.enums import JobStatus, JobType, VideoStatus
from services.pipeline import assemble, render_avatar, resolve_broll

logger = logging.getLogger("contentos.scheduler")


def _try_redis_lock(interval: int) -> bool:
    try:
        import redis

        client = redis.from_url(get_settings().redis_url, socket_connect_timeout=0.4)
        return bool(client.set("contentos:scheduler", "1", nx=True, ex=max(interval, 5)))
    except Exception:
        return True


def tick_once() -> int:
    """Advance leftover queued simulated jobs. Instant path usually finishes in-request."""
    db = SessionLocal()
    advanced = 0
    try:
        jobs = (
            db.query(RenderJob)
            .filter(RenderJob.status == JobStatus.QUEUED.value)
            .limit(25)
            .all()
        )
        for job in jobs:
            video = db.get(VideoProject, job.video_id) if job.video_id else None
            workspace = db.get(Workspace, job.workspace_id)
            if not video or not workspace:
                job.status = JobStatus.FAILED.value
                job.error = "missing video or workspace"
                db.commit()
                advanced += 1
                continue
            try:
                if job.job_type == JobType.AVATAR.value and video.status in {
                    VideoStatus.SCRIPT_APPROVED.value,
                    VideoStatus.RENDERING_AVATAR.value,
                }:
                    render_avatar(db, workspace, video)
                    advanced += 1
                elif job.job_type == JobType.BROLL.value and video.status == VideoStatus.AVATAR_READY.value:
                    resolve_broll(db, workspace, video)
                    advanced += 1
                elif job.job_type == JobType.ASSEMBLY.value and video.status == VideoStatus.RESOLVING_BROLL.value:
                    assemble(db, workspace, video)
                    advanced += 1
                else:
                    job.status = JobStatus.COMPLETED.value
                    job.result_payload = {"note": "scheduler skipped stale job"}
                    job.updated_at = datetime.now(timezone.utc)
                    db.commit()
                    advanced += 1
            except Exception as exc:
                db.rollback()
                logger.warning("scheduler job %s failed: %s", job.id, exc)
        return advanced
    finally:
        db.close()


async def scheduler_loop() -> None:
    settings = get_settings()
    interval = max(settings.scheduler_interval_seconds, 5)
    logger.info("scheduler loop every %ss", interval)
    while True:
        try:
            if _try_redis_lock(interval):
                tick_once()
        except Exception:
            logger.exception("scheduler tick failed")
        await asyncio.sleep(interval)
