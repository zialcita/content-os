import hashlib
import json
from types import SimpleNamespace
from uuid import UUID,uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.exc import DBAPIError

from conftest import onboard,brand,invite,PREFIX
from content_core.router import create_router
from content_core.workbench import create_workbench_router
from content_core.storage import LocalStore,StorageError,PART_BYTES
from content_core.worker import IngestionWorker,call
from content_core.security import audit_content_privileges


@pytest.fixture
def workflow(api,tmp_path):
    store=LocalStore(tmp_path/'private',development=True)
    api.app.include_router(create_router(store))
    api.app.include_router(create_workbench_router())
    role='fixture_content_'+uuid4().hex
    with api.db.engine.begin() as c:
        c.exec_driver_sql(f'CREATE ROLE {role} LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS')
        c.exec_driver_sql(f'GRANT cos_content_worker TO {role}')
    engine=create_engine(api.db.runtime.url.set(username=role),hide_parameters=True)
    owner=api.login(); w=onboard(api,owner)['workspace_id']; b=brand(owner,w)['brand_id']
    value=SimpleNamespace(api=api,owner=owner,w=w,b=b,base=PREFIX+f'/workspaces/{w}/brands/{b}',store=store,
                          worker=IngestionWorker(engine,store),engine=engine)
    yield value
    engine.dispose();store.close()


def start(t,data=b'An original source for a client campaign.\n',mime='text/plain',digest=None,key=None,client=None):
    client=client or t.owner.client
    result=client.post(t.base+'/upload-intents',json={'title':'Campaign source','mime_type':mime,'size_bytes':len(data),
         'sha256':digest or hashlib.sha256(data).hexdigest(),'rights_assertion':'I own this test material.'},headers={'Idempotency-Key':key or str(uuid4())})
    assert result.status_code==201,result.text
    return result.json()


def transfer(t,u,data,client=None):
    client=client or t.owner.client
    for number,offset in enumerate(range(0,len(data),PART_BYTES),1):
        response=client.put(t.base+f'/upload-intents/{u["upload_id"]}/parts/{number}',content=data[offset:offset+PART_BYTES],
                            headers={'If-Match':'"'+str(u['revision'])+'"','Content-Type':'application/octet-stream'})
        assert response.status_code==200,response.text
        u=response.json()
    return u


def finalize(t,u,key=None):
    response=t.owner.client.post(t.base+f'/sources/{u["source_asset_id"]}/finalize',json={'upload_id':u['upload_id']},
            headers={'If-Match':'"'+str(u['revision'])+'"','Idempotency-Key':key or str(uuid4())})
    assert response.status_code==202,response.text
    return response.json()


def test_login_upload_worker_preview_and_immutable_revision(workflow):
    t=workflow;data='A real UTF-8 source: Mānoa and Ontario.\nNo generated claims.'.encode()
    u=transfer(t,start(t,data),data); acknowledgement=finalize(t,u)
    queued=t.owner.client.get(acknowledgement['status_url']).json()
    assert queued['status']=='QUEUED' and queued['result_version_id'] is None
    source=t.owner.client.get(t.base+'/sources/'+u['source_asset_id']).json()
    assert source['current_version_id'] is None
    done=t.worker.process_one(t.w,t.b)
    assert done['status']=='SUCCEEDED',done
    source=t.owner.client.get(t.base+'/sources/'+u['source_asset_id']).json()
    version=source['current_version_id']
    preview=t.owner.client.get(t.base+f'/sources/{u["source_asset_id"]}/versions/{version}/content')
    assert preview.status_code==200,preview.text
    assert preview.json()['text']==data.decode() and preview.json()['antivirus_certified'] is False
    old=t.owner.client.get(t.base+'/source-versions/'+version).json()
    assert old['sealed'] is True and 'object_key' not in old['snapshot']
    edited=t.owner.client.patch(t.base+'/sources/'+u['source_asset_id'],json={'title':'Reviewed source title','rights_assertion':'Owned source; reviewed'},
             headers={'If-Match':'"'+str(source['revision'])+'"','Idempotency-Key':str(uuid4())})
    assert edited.status_code==200,edited.text
    assert edited.json()['version_id']!=version
    assert t.owner.client.get(t.base+'/source-versions/'+version).json()==old
    with t.api.db.engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM cos_v6.dependency_edges WHERE workspace_id=:w'),{'w':UUID(t.w)}).scalar_one()==1
    artifact={'workflow':'OIDC fixture login → real PostgreSQL workspace/brand → private file upload → queued job → separate worker → immutable version → exact text preview → metadata revision',
              'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'queued':queued['status'],'completed':done['status'],
              'text_policy':'TEXT_POLICY_V1, not antivirus certification','real_provider_calls':0,'real_file_processed':True,'version_before':version,'version_after':edited.json()['version_id']}
    from conftest import EVIDENCE
    (EVIDENCE/'workflow.json').write_text(json.dumps(artifact,indent=2))
    (EVIDENCE/'runtime.openapi.json').write_text(json.dumps(t.api.app.openapi(),indent=2))


def test_resume_and_replay_do_not_duplicate(workflow):
    t=workflow; data=b'a'*(PART_BYTES+17);key=str(uuid4())
    u=start(t,data,key=key);assert start(t,data,key=key)['upload_id']==u['upload_id']
    first=t.owner.client.put(t.base+f'/upload-intents/{u["upload_id"]}/parts/1',content=data[:PART_BYTES],headers={'If-Match':'"1"'})
    assert first.status_code==200,first.text
    again=t.owner.client.put(t.base+f'/upload-intents/{u["upload_id"]}/parts/1',content=data[:PART_BYTES],headers={'If-Match':'"1"'})
    assert again.status_code==200 and again.json()['revision']==2
    current=t.owner.client.get(t.base+'/upload-intents/'+u['upload_id']).json()
    second=t.owner.client.put(t.base+f'/upload-intents/{u["upload_id"]}/parts/2',content=data[PART_BYTES:],headers={'If-Match':'"2"'})
    assert second.status_code==200,second.text
    fkey=str(uuid4()); a=finalize(t,second.json(),fkey);b=finalize(t,second.json(),fkey)
    assert a['job_id']==b['job_id']
    assert t.worker.process_one(t.w,t.b)['status']=='SUCCEEDED'


@pytest.mark.parametrize('failure',['hash','binary','missing_scanner','pdf'])
def test_bad_or_unscannable_content_never_becomes_ready(workflow,failure):
    t=workflow; data=b'Bad\x00binary' if failure=='binary' else b'%PDF-1.7 incomplete' if failure=='pdf' else b'Example source'
    u=start(t,data,digest='0'*64 if failure=='hash' else None,mime='application/pdf' if failure=='pdf' else 'text/plain')
    u=transfer(t,u,data);finalize(t,u)
    if failure=='missing_scanner':t.worker.text_policy=False
    done=t.worker.process_one(t.w,t.b)
    assert done['status'] in ('REJECTED','BLOCKED') and done['result_version_id'] is None
    source=t.owner.client.get(t.base+'/sources/'+u['source_asset_id']).json()
    assert source['current_version_id'] is None


def test_cross_tenant_and_viewer_cannot_mutate(workflow):
    t=workflow; u=start(t)
    stranger=t.api.login()
    assert stranger.client.get(t.base+'/upload-intents/'+u['upload_id']).status_code==404
    viewer,_,_=invite(t.api,t.owner,t.w,[t.b],roles=['VIEWER'])
    assert viewer.client.get(t.base+'/upload-intents/'+u['upload_id']).status_code==200
    denied=viewer.client.put(t.base+f'/upload-intents/{u["upload_id"]}/parts/1',content=b'x',headers={'If-Match':'"1"'})
    assert denied.status_code in (403,404)
    assert not t.store.root.joinpath(t.w,t.b,u['upload_id']).exists()


def test_cancel_fences_worker_and_purges_only_own_file(workflow):
    t=workflow;data=b'Cancel this';u=transfer(t,start(t,data),data);finalize(t,u)
    with t.engine.begin() as c: claimed=call(c,'cc_claim',w=UUID(t.w),b=UUID(t.b))
    current=t.owner.client.get(t.base+'/upload-intents/'+u['upload_id']).json()
    result=t.owner.client.post(t.base+'/upload-intents/'+u['upload_id']+'/cancel',headers={'If-Match':'"'+str(current['revision'])+'"'})
    assert result.status_code==200,result.text
    with pytest.raises(DBAPIError):
        with t.engine.begin() as c: call(c,'cc_finish',w=UUID(t.w),b=UUID(t.b),jid=UUID(claimed['job_id']),cap=claimed['claim'],fence=claimed['fence'],
            outcome='CLEAR',h=hashlib.sha256(data).digest(),sz=len(data),mime='text/plain',scanner='TEXT_POLICY_V1',probe='UTF8_BOUNDS_V1')
    t.worker.process_one(t.w,t.b)
    with pytest.raises(StorageError):t.store.read_part(t.w+'/'+t.b+'/'+u['upload_id'],1)


def test_expired_worker_reclaim_has_new_fence(workflow):
    t=workflow;data=b'Recover safely';u=transfer(t,start(t,data),data);a=finalize(t,u)
    with t.engine.begin() as c: old=call(c,'cc_claim',w=UUID(t.w),b=UUID(t.b))
    with t.api.db.engine.begin() as c:c.execute(text("UPDATE cos_v6.ingestion_jobs SET lease_expires_at=clock_timestamp()-interval '1 second' WHERE id=:j"),{'j':UUID(a['job_id'])})
    done=t.worker.process_one(t.w,t.b);assert done['status']=='SUCCEEDED'
    with pytest.raises(DBAPIError):
        with t.engine.begin() as c:call(c,'cc_heartbeat',w=UUID(t.w),b=UUID(t.b),jid=UUID(old['job_id']),cap=old['claim'],fence=old['fence'])


def test_immutable_version_and_missing_subtype_rejected(workflow):
    t=workflow;data=b'Immutable';u=transfer(t,start(t,data),data);finalize(t,u);done=t.worker.process_one(t.w,t.b)
    with pytest.raises(DBAPIError):
        with t.api.db.engine.begin() as c:c.execute(text("UPDATE cos_v6.source_versions SET title='tampered' WHERE id=:v"),{'v':UUID(done['result_version_id'])})
    with pytest.raises(DBAPIError):
        with t.api.db.engine.begin() as c:
            c.execute(text("INSERT INTO cos_v6.version_registry(workspace_id,brand_id,kind,snapshot,content_hash,sealed,sealed_at,created_by_membership_id,origin) SELECT :w,:b,'source','{}',:h,true,clock_timestamp(),owner_membership_id,'USER' FROM cos_v6.workspaces WHERE id=:w"),{'w':UUID(t.w),'b':UUID(t.b),'h':b'x'*32})


def test_content_privilege_audit_denies_public_grant(workflow):
    t=workflow
    with pytest.raises(RuntimeError):
        with t.api.db.engine.begin() as c:
            c.exec_driver_sql('GRANT EXECUTE ON FUNCTION cos_v6.cc_claim(uuid,uuid) TO PUBLIC')
            audit_content_privileges(c)
