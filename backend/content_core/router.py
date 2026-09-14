"""Scoped private upload API; compose with the secure identity factory."""
import asyncio
import hashlib
from uuid import UUID
from fastapi import APIRouter,Request,Response,Query
from pydantic import BaseModel,ConfigDict,Field,model_validator
from starlette.concurrency import run_in_threadpool
from secure_api.dependencies import get_scope
from secure_api.errors import APIError,STATUS
from . import models as M
from .worker import call
from .storage import StorageError,PART_BYTES

for code in ('UPLOAD_NOT_WRITABLE','UPLOAD_INCOMPLETE','QUARANTINED','INVALID_PART','STORAGE_QUOTA_EXCEEDED',
             'REGISTRY_INCOMPLETE','SOURCE_NOT_VALIDATED','LINEAGE_MISMATCH','DEPENDENCY_CYCLE','IMMUTABLE_VERSION',
             'SCANNER_UNCONFIGURED','VALIDATION_MISMATCH','PROCESSING_LIMIT'):
    STATUS[code]=422
for code in ('STALE_CLAIM','AUTHORITY_REVOKED'): STATUS[code]=409


class Model(BaseModel): model_config=ConfigDict(extra='forbid')
class Upload(Model):
    title:str=Field(min_length=1,max_length=200)
    mime_type:str
    size_bytes:int=Field(ge=1,le=2000000000,strict=True)
    sha256:str=Field(pattern='^[0-9a-f]{64}$')
    rights_assertion:str=Field(min_length=1,max_length=2000)
    @model_validator(mode='after')
    def document_limit(self):
        if self.mime_type in ('text/plain','application/pdf') and self.size_bytes>50000000:
            raise ValueError('Text/PDF source exceeds 50 MB')
        return self
class Finalize(Model): upload_id:UUID
class Revision(Model):
    title:str=Field(min_length=1,max_length=200)
    rights_assertion:str=Field(min_length=1,max_length=2000)


def expected(request):
    raw=request.headers.get('if-match')
    if raw is None: raise APIError('PRECONDITION_REQUIRED',428)
    if len(raw)>21 or not (raw.startswith('"') and raw.endswith('"')) or not raw[1:-1].isascii() or not raw[1:-1].isdigit():
        raise APIError('INVALID_ETAG',422)
    n=int(raw[1:-1])
    if not 1<=n<=9223372036854775807: raise APIError('INVALID_ETAG',422)
    return n


def replay_key(request):
    key=request.headers.get('idempotency-key','')
    if not 1<=len(key)<=200: raise APIError('IDEMPOTENCY_KEY_REQUIRED',422)
    return key


def create_router(store):
    r=APIRouter(prefix='/api/v6/workspaces/{workspace_id}/brands/{brand_id}',tags=['Private sources'])
    def scoped(request,w,b,action='read'): return get_scope(request,w,b,action).connection
    def response_etag(response,value):
        if 'revision' in value: response.headers['ETag']='"'+str(value['revision'])+'"'
        return value

    @r.post('/upload-intents',status_code=201,response_model=M.UploadResult,operation_id='createUploadIntent')
    def create(workspace_id:UUID,brand_id:UUID,body:Upload,request:Request,response:Response):
        if store is None: raise APIError('STORAGE_UNCONFIGURED',503)
        if body.mime_type not in ('text/plain','application/pdf','audio/wav','video/mp4'): raise APIError('UNSUPPORTED_MEDIA_TYPE',422)
        result=call(scoped(request,workspace_id,brand_id,'edit'),'cc_create_upload',w=workspace_id,b=brand_id,ttl=body.title,
                    mime=body.mime_type,sz=body.size_bytes,h=bytes.fromhex(body.sha256),rights=body.rights_assertion,key=replay_key(request))
        return response_etag(response,result)

    @r.get('/upload-intents/{upload_id}',response_model=M.UploadResult,operation_id='getUploadIntent')
    def upload(workspace_id:UUID,brand_id:UUID,upload_id:UUID,request:Request,response:Response):
        return response_etag(response,call(scoped(request,workspace_id,brand_id),'cc_read',w=workspace_id,b=brand_id,kind='upload',target=upload_id))

    @r.put('/upload-intents/{upload_id}/parts/{part_number}',response_model=M.UploadResult,operation_id='putLocalUploadPart')
    async def put_part(workspace_id:UUID,brand_id:UUID,upload_id:UUID,part_number:int,request:Request,response:Response):
        if store is None: raise APIError('STORAGE_UNCONFIGURED',503)
        revision=expected(request)
        c=await run_in_threadpool(scoped,request,workspace_id,brand_id,'edit')
        grant=await run_in_threadpool(call,c,'cc_transfer',w=workspace_id,b=brand_id,i=upload_id,n=part_number)
        try:
            content_length=int(request.headers.get('content-length','0'))
            if content_length>grant['size_bytes']: raise APIError('INVALID_PART',422)
        except ValueError: raise APIError('INVALID_PART',422) from None
        data=bytearray()
        try:
            async with asyncio.timeout(30):
                async for chunk in request.stream():
                    if len(data)+len(chunk)>grant['size_bytes']: raise APIError('INVALID_PART',422)
                    data.extend(chunk)
        except TimeoutError: raise APIError('PROCESSING_LIMIT',422) from None
        if len(data)!=grant['size_bytes']: raise APIError('INVALID_PART',422)
        digest=hashlib.sha256(data).digest()
        result=await run_in_threadpool(call,c,'cc_record_part',w=workspace_id,b=brand_id,i=upload_id,n=part_number,sz=len(data),h=digest,expected=revision)
        try: await run_in_threadpool(store.write_part,grant['key'],part_number,bytes(data))
        except StorageError: raise APIError('STORAGE_INVALID',409) from None
        # DB metadata commits only after the file is durable; rollback leaves a bounded retryable orphan.
        return response_etag(response,result)

    @r.post('/sources/{source_id}/finalize',status_code=202,response_model=M.AsyncResult,operation_id='finalizeSource')
    def finalize(workspace_id:UUID,brand_id:UUID,source_id:UUID,body:Finalize,request:Request,response:Response):
        result=call(scoped(request,workspace_id,brand_id,'edit'),'cc_finalize',w=workspace_id,b=brand_id,sid=source_id,
                    i=body.upload_id,expected=expected(request),key=replay_key(request))
        url=f'/api/v6/workspaces/{workspace_id}/brands/{brand_id}/ingestion-jobs/{result["job_id"]}'
        response.headers['Location']=url;response.headers['Retry-After']='1'
        return {**result,'status_url':url,'correlation_id':request.state.correlation_id}

    @r.post('/upload-intents/{upload_id}/cancel',response_model=M.UploadResult,operation_id='cancelUploadIntent')
    def cancel(workspace_id:UUID,brand_id:UUID,upload_id:UUID,request:Request,response:Response):
        return response_etag(response,call(scoped(request,workspace_id,brand_id,'edit'),'cc_cancel',w=workspace_id,b=brand_id,i=upload_id,expected=expected(request)))

    @r.get('/ingestion-jobs/{job_id}',response_model=M.JobResult,operation_id='getIngestionJob')
    def job(workspace_id:UUID,brand_id:UUID,job_id:UUID,request:Request):
        return call(scoped(request,workspace_id,brand_id),'cc_read',w=workspace_id,b=brand_id,kind='job',target=job_id)

    @r.get('/sources/{source_id}',response_model=M.SourceResult,operation_id='getPrivateSource')
    def source(workspace_id:UUID,brand_id:UUID,source_id:UUID,request:Request,response:Response):
        return response_etag(response,call(scoped(request,workspace_id,brand_id),'cc_read',w=workspace_id,b=brand_id,kind='source',target=source_id))

    @r.get('/source-versions/{version_id}',response_model=M.VersionResult,operation_id='getPrivateSourceVersion')
    def version(workspace_id:UUID,brand_id:UUID,version_id:UUID,request:Request):
        return call(scoped(request,workspace_id,brand_id),'cc_read',w=workspace_id,b=brand_id,kind='version',target=version_id)

    @r.patch('/sources/{source_id}',response_model=M.RevisionResult,operation_id='reviseSourceMetadata')
    def revise(workspace_id:UUID,brand_id:UUID,source_id:UUID,body:Revision,request:Request,response:Response):
        result=call(scoped(request,workspace_id,brand_id,'edit'),'cc_revise',w=workspace_id,b=brand_id,sid=source_id,
                    ttl=body.title,rights=body.rights_assertion,expected=expected(request),key=replay_key(request))
        return response_etag(response,result)

    @r.get('/sources/{source_id}/versions/{version_id}/content',response_model=M.PreviewResult,operation_id='getPrivateSourceContent')
    def content(workspace_id:UUID,brand_id:UUID,source_id:UUID,version_id:UUID,request:Request,limit:int=Query(100000,ge=1,le=100000)):
        grant=call(scoped(request,workspace_id,brand_id),'cc_download',w=workspace_id,b=brand_id,sid=source_id,v=version_id)
        if store is None: raise APIError('STORAGE_UNCONFIGURED',503)
        if grant['mime_type']!='text/plain': raise APIError('UNSUPPORTED_MEDIA_TYPE',422)
        try:
            data=bytearray()
            for chunk in store.chunks(grant['key'],grant['parts']):
                data.extend(chunk)
                if len(data)>=limit*4: break
            value=data.decode('utf8',errors='replace')
        except StorageError: raise APIError('STORAGE_INVALID',503) from None
        return {'text':value[:limit],'truncated':len(value)>limit or len(data)<grant['size_bytes'],'size_bytes':grant['size_bytes'],
                'sha256':grant['sha256'],'validation':'TEXT_POLICY_V1','antivirus_certified':False}
    return r
