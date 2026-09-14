from datetime import datetime
from typing import Literal,Any
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field

class Model(BaseModel): model_config=ConfigDict(extra='forbid')
class Part(Model):
    part_number:int=Field(ge=1,le=256)
    size_bytes:int=Field(ge=1,le=8388608)
    sha256:str=Field(pattern='^[0-9a-f]{64}$')
class UploadResult(Model):
    upload_id:UUID
    workspace_id:UUID
    brand_id:UUID
    source_asset_id:UUID
    state:Literal['UPLOADING','QUEUED','SCANNING','CLEARED','BLOCKED','REJECTED','CANCELLED','PURGED']
    revision:int=Field(ge=1)
    expected_size:int=Field(ge=1,le=2000000000)
    expected_sha256:str
    mime_type:str
    execution_mode:Literal['LOCAL_PRIVATE_DEVELOPMENT']
    expires_at:datetime
    expired:bool
    source_version_id:UUID|None
    error_code:str|None
    parts:list[Part]
class AsyncResult(Model):
    job_id:UUID
    state:Literal['QUEUED']
    upload_id:UUID
    revision:int
    status_url:str
    correlation_id:UUID
class JobEvent(Model):
    state:str
    occurred_at:datetime
    fence:int
class JobResult(Model):
    job_id:UUID
    workspace_id:UUID
    brand_id:UUID
    upload_id:UUID
    job_kind:Literal['INGEST','PURGE_CANCELLED_UPLOAD']
    status:Literal['QUEUED','RUNNING','SUCCEEDED','BLOCKED','REJECTED','CANCELLED']
    execution_mode:Literal['LOCAL_PRIVATE_DEVELOPMENT']
    paid_authority:Literal['NONE']
    attempts:int
    error_code:str|None
    result_version_id:UUID|None
    events:list[JobEvent]
class SourceResult(Model):
    source_asset_id:UUID
    workspace_id:UUID
    brand_id:UUID
    title:str
    current_version_id:UUID|None
    revision:int
    upload:UploadResult
class SourceSnapshot(Model):
    schema_version:Literal[1]
    source_asset_id:UUID
    version_no:int
    upload_id:UUID
    previous_version_id:UUID|None
    sha256:str
    size_bytes:int
    mime_type:str
    title:str
    rights_assertion:str
class VersionResult(Model):
    version_id:UUID
    kind:Literal['source']
    sealed:Literal[True]
    content_hash:str
    snapshot:SourceSnapshot
    origin:Literal['USER','FIXTURE']
    created_at:datetime
class RevisionResult(Model):
    source_asset_id:UUID
    version_id:UUID
    revision:int
class PreviewResult(Model):
    text:str
    truncated:bool
    size_bytes:int
    sha256:str
    validation:Literal['TEXT_POLICY_V1']
    antivirus_certified:Literal[False]
