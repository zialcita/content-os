import os
import secrets
from uuid import UUID,uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from alembic import command
from alembic.config import Config

from conftest import ROOT,PREFIX,invite
from test_workflow import workflow,start,transfer,finalize
from content_core.storage import LocalStore,StorageError
from content_core.security import guard_worker
from foundation.migration_audit import audit_migrated_privileges


def test_csrf_incomplete_upload_and_conflicting_idempotency(workflow):
    t=workflow;data=b'bounded';key=str(uuid4());u=start(t,data,key=key)
    response=t.owner.client.post(t.base+'/upload-intents',json={'title':'different','mime_type':'text/plain','size_bytes':len(data),
         'sha256':u['expected_sha256'],'rights_assertion':'owned'},headers={'Idempotency-Key':key})
    assert response.status_code==409
    bad=t.owner.client.put(t.base+f'/upload-intents/{u["upload_id"]}/parts/1',content=data,headers={'If-Match':'"1"','X-CSRF-Token':''})
    assert bad.status_code==403
    incomplete=t.owner.client.post(t.base+f'/sources/{u["source_asset_id"]}/finalize',json={'upload_id':u['upload_id']},
              headers={'If-Match':'"1"','Idempotency-Key':str(uuid4())})
    assert incomplete.status_code==422 and incomplete.json()['code']=='UPLOAD_INCOMPLETE'
    oversized=t.owner.client.put(t.base+f'/upload-intents/{u["upload_id"]}/parts/1',content=data+b'extra',headers={'If-Match':'"1"'})
    assert oversized.status_code==422


def test_revoked_editor_job_is_blocked_before_processing(workflow):
    t=workflow;editor,m,_=invite(t.api,t.owner,t.w,[t.b],roles=['EDITOR'])
    u=start(t,b'editor owned',client=editor.client);u=transfer(t,u,b'editor owned',client=editor.client)
    finalized=editor.client.post(t.base+f'/sources/{u["source_asset_id"]}/finalize',json={'upload_id':u['upload_id']},
          headers={'If-Match':'"'+str(u['revision'])+'"','Idempotency-Key':str(uuid4())})
    assert finalized.status_code==202
    revoked=t.owner.client.delete(PREFIX+f'/workspaces/{t.w}/memberships/{m["membership_id"]}',headers={'If-Match':'"'+str(m['revision'])+'"'})
    assert revoked.status_code==200
    done=t.worker.process_one(t.w,t.b);assert done['status']=='BLOCKED'
    assert t.owner.client.get(t.base+'/sources/'+u['source_asset_id']).json()['current_version_id'] is None
    assert editor.client.get(t.base+'/upload-intents/'+u['upload_id']).status_code==404


def test_zero_storage_quota_and_cross_brand_reference_denied(workflow):
    t=workflow
    with t.api.db.engine.begin() as c:
        c.execute(text('INSERT INTO cos_v6.content_capacity(workspace_id,limit_bytes) VALUES(:w,0)'),{'w':UUID(t.w)})
    response=t.owner.client.post(t.base+'/upload-intents',json={'title':'denied','mime_type':'text/plain','size_bytes':1,'sha256':'0'*64,'rights_assertion':'owned'},headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==422 and response.json()['code']=='STORAGE_QUOTA_EXCEEDED'
    with pytest.raises(DBAPIError):
        with t.api.db.engine.begin() as c:c.execute(text('INSERT INTO cos_v6.source_assets(workspace_id,brand_id,title,created_by_membership_id) SELECT id,:b,\'bad\',owner_membership_id FROM cos_v6.workspaces WHERE id=:w'),{'w':UUID(t.w),'b':uuid4()})


def test_symlink_hardlink_fifo_and_world_readable_storage_refused(workflow,tmp_path):
    t=workflow;key=t.w+'/'+t.b+'/'+str(uuid4());outside=tmp_path/'outside';outside.write_bytes(b'private outside bytes')
    fd=t.store.directory(key,True);os.close(fd)
    target=t.store.root/key/'0001.part'
    target.symlink_to(outside)
    with pytest.raises(StorageError):t.store.read_part(key,1)
    target.unlink();os.link(outside,target)
    with pytest.raises(StorageError):t.store.read_part(key,1)
    target.unlink();os.mkfifo(target,0o600)
    with pytest.raises(StorageError):t.store.read_part(key,1)
    target.unlink()
    assert outside.read_bytes()==b'private outside bytes'
    broad=tmp_path/'world';broad.mkdir();broad.chmod(0o777)
    with pytest.raises(StorageError):LocalStore(broad,development=True)


def test_cancel_reclaims_quota_and_keeps_unrelated_upload(workflow):
    t=workflow;data=b'keep';keep=transfer(t,start(t,data),data);discard=transfer(t,start(t,data),data)
    t.owner.client.post(t.base+'/upload-intents/'+discard['upload_id']+'/cancel',headers={'If-Match':'"'+str(discard['revision'])+'"'})
    assert t.worker.process_one(t.w,t.b)['status']=='SUCCEEDED'
    assert t.store.read_part(t.w+'/'+t.b+'/'+keep['upload_id'],1)==data
    with t.api.db.engine.connect() as c:assert c.execute(text('SELECT reserved_bytes FROM cos_v6.content_capacity WHERE workspace_id=:w'),{'w':UUID(t.w)}).scalar_one()==len(data)


def test_workflow_ui_does_not_interpret_source_html(workflow):
    t=workflow;data=b'<script>alert("not executable")</script>'
    u=transfer(t,start(t,data),data);finalize(t,u);done=t.worker.process_one(t.w,t.b)
    preview=t.owner.client.get(t.base+f'/sources/{u["source_asset_id"]}/versions/{done["result_version_id"]}/content')
    assert preview.headers['content-type'].startswith('application/json')
    assert preview.json()['text']==data.decode()
    html=t.owner.client.get(PREFIX+'/workflow').text
    assert "$('preview').textContent=" in html and 'innerHTML' not in html


def test_full_head_rerun_and_unsafe_runtime_grant_are_audited(workflow):
    t=workflow
    with t.api.db.engine.begin() as c:
        cfg=Config(str(ROOT/'backend/alembic.ini'));cfg.attributes['connection']=c
        command.upgrade(cfg,'head');audit_migrated_privileges(c)
        assert c.execute(text('SELECT version_num FROM public.cos_v6_alembic_version')).scalar_one()=='0003_content_core'
    with pytest.raises(RuntimeError):
        with t.api.db.engine.begin() as c:
            c.exec_driver_sql('GRANT SELECT ON cos_v6.upload_intents TO cos_api_runtime')
            audit_migrated_privileges(c)


def test_ui_rejects_backslash_return_path(workflow):
    response=workflow.owner.client.post(PREFIX+'/auth/login',json={'return_path':'/'+chr(92)+'attacker.invalid'})
    assert response.status_code==422


def test_oversized_document_rejected_before_reserving_storage(workflow):
    t=workflow
    response=t.owner.client.post(t.base+'/upload-intents',json={'title':'too large','mime_type':'text/plain','size_bytes':50000001,'sha256':'0'*64,'rights_assertion':'owned'},headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==422
    with t.api.db.engine.connect() as c:assert c.execute(text('SELECT count(*) FROM cos_v6.content_capacity WHERE workspace_id=:w'),{'w':UUID(t.w)}).scalar_one()==0


def test_worker_login_cannot_have_schema_create(workflow):
    t=workflow
    with t.engine.connect() as c:role=c.execute(text('SELECT current_user')).scalar_one()
    assert role.startswith('fixture_content_')
    with t.api.db.engine.begin() as c:c.exec_driver_sql(f'GRANT CREATE ON SCHEMA cos_v6 TO {role}')
    with pytest.raises(RuntimeError,match='schema creation'):guard_worker(t.engine)
    with t.api.db.engine.begin() as c:c.exec_driver_sql(f'REVOKE CREATE ON SCHEMA cos_v6 FROM {role}')
