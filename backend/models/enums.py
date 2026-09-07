from enum import Enum


class VideoStatus(str, Enum):
    SCRIPTING = "scripting"
    SCRIPT_READY = "script_ready"
    SCRIPT_APPROVED = "script_approved"
    RENDERING_AVATAR = "rendering_avatar"
    AVATAR_READY = "avatar_ready"
    RESOLVING_BROLL = "resolving_broll"
    ASSEMBLING = "assembling"
    ASSEMBLY_READY = "assembly_ready"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"


FORWARD: dict[VideoStatus, tuple[VideoStatus, ...]] = {
    VideoStatus.SCRIPTING: (VideoStatus.SCRIPT_READY, VideoStatus.FAILED),
    VideoStatus.SCRIPT_READY: (VideoStatus.SCRIPT_APPROVED, VideoStatus.SCRIPTING, VideoStatus.FAILED),
    VideoStatus.SCRIPT_APPROVED: (VideoStatus.RENDERING_AVATAR, VideoStatus.FAILED),
    VideoStatus.RENDERING_AVATAR: (VideoStatus.AVATAR_READY, VideoStatus.FAILED),
    VideoStatus.AVATAR_READY: (VideoStatus.RESOLVING_BROLL, VideoStatus.FAILED),
    VideoStatus.RESOLVING_BROLL: (VideoStatus.ASSEMBLING, VideoStatus.FAILED),
    VideoStatus.ASSEMBLING: (VideoStatus.ASSEMBLY_READY, VideoStatus.FAILED),
    VideoStatus.ASSEMBLY_READY: (VideoStatus.IN_REVIEW, VideoStatus.FAILED),
    VideoStatus.IN_REVIEW: (VideoStatus.APPROVED, VideoStatus.FAILED),
    VideoStatus.APPROVED: (VideoStatus.PUBLISHING, VideoStatus.FAILED),
    VideoStatus.PUBLISHING: (VideoStatus.PUBLISHED, VideoStatus.FAILED),
    VideoStatus.PUBLISHED: (),
    VideoStatus.FAILED: (),
}


class JobType(str, Enum):
    SCRIPT = "script"
    AVATAR = "avatar"
    BROLL = "broll"
    ASSEMBLY = "assembly"
    CLIP = "clip"
    PUBLISH = "publish"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AssetKind(str, Enum):
    AROLL = "aroll"
    BROLL = "broll"
    ASSEMBLY = "assembly"
    CLIP = "clip"
    THUMB = "thumb"
    OTHER = "other"


class AssetSource(str, Enum):
    LIBRARY = "library"
    PEXELS = "pexels"
    HIGGSFIELD = "higgsfield"
    HEYGEN = "heygen"
    SHOTSTACK = "shotstack"
    UPLOAD = "upload"
    YOUTUBE = "youtube"
    SIMULATED = "simulated"
