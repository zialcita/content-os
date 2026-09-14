import secrets
from uuid import UUID, uuid4
from sqlalchemy import text
from conftest import PREFIX, COOKIE, ISSUER, onboard, brand, invite
from secure_api.app import digest


def test_brand_ifmatch_and_idempotency_persisted_once(api):
    owner=api.login(); w=onboard(api,owner)['workspace_id']; c=owner.client
    path=PREFIX+f'/workspaces/{w}/brands'; body={'name':'one','timezone':'UTC'}
    assert c.post(path,json=body).json()['code']=='IDEMPOTENCY_KEY_REQUIRED'
    key=str(uuid4()); r=c.post(path,json=body,headers={'Idempotency-Key':key})
    assert r.status_code==201,r.text
    replay=c.post(path,json=body,headers={'Idempotency-Key':key})
    assert replay.status_code==201 and replay.json()==r.json()
    conflict=c.post(path,json={**body,'name':'different'},headers={'Idempotency-Key':key})
    assert conflict.status_code==409 and conflict.json()['code']=='IDEMPOTENCY_CONFLICT'
    b=r.json()['brand_id']; path+='/'+b
    assert c.patch(path,json=body,headers={'Idempotency-Key':str(uuid4())}).status_code==428
    for value in ('*','W/"1"','1','"0"','"no"'):
        assert c.patch(path,json=body,headers={'Idempotency-Key':str(uuid4()),'If-Match':value}).status_code==422
    update_key=str(uuid4()); headers={'Idempotency-Key':update_key,'If-Match':'"1"'}
    updated=c.patch(path,json={**body,'name':'two'},headers=headers)
    assert updated.status_code==200 and updated.headers['ETag']=='"2"',updated.text
    # Replay is recognized before stale If-Match; response remains original.
    replay=c.patch(path,json={**body,'name':'two'},headers=headers)
    assert replay.json()==updated.json() and replay.status_code==200
    stale=c.patch(path,json=body,headers={'Idempotency-Key':str(uuid4()),'If-Match':'"1"'})
    assert stale.status_code==409 and stale.json()['code']=='STALE_VERSION'
    with api.db.engine.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM cos_v6.brands WHERE workspace_id=:w'),{'w':UUID(w)}).scalar_one()==1
        assert conn.execute(text('SELECT identity_revision FROM cos_v6.brands WHERE id=:b'),{'b':UUID(b)}).scalar_one()==2
        assert conn.execute(text('SELECT count(*) FROM cos_v6.identity_replays WHERE workspace_id=:w'),{'w':UUID(w)}).scalar_one()==2


def test_cursor_pagination_scoped_signed_and_limit(api):
    owner=api.login(); w=onboard(api,owner)['workspace_id']
    ids=[brand(owner,w)['brand_id'] for _ in range(3)]
    path=PREFIX+f'/workspaces/{w}/brands'
    first=owner.client.get(path,params={'limit':1}).json()
    assert first['has_more'] and first['next_cursor'] and len(first['items'])==1
    second=owner.client.get(path,params={'limit':1,'cursor':first['next_cursor']}).json()
    third=owner.client.get(path,params={'limit':1,'cursor':second['next_cursor']}).json()
    assert not third['has_more'] and third['next_cursor'] is None
    assert {x['items'][0]['brand_id'] for x in (first,second,third)}==set(ids)
    assert owner.client.get(path,params={'cursor':first['next_cursor']+'x'}).status_code==422
    w2=onboard(api,owner)['workspace_id']
    assert owner.client.get(PREFIX+f'/workspaces/{w2}/brands',params={'cursor':first['next_cursor']}).status_code==422
    for limit in (0,101): assert owner.client.get(path,params={'limit':limit}).status_code==422


def test_admin_explicit_brand_grants_and_combined_roles(api):
    owner=api.login(); w=onboard(api,owner)['workspace_id']; b=brand(owner,w)['brand_id']; hidden=brand(owner,w)['brand_id']
    admin,m,_=invite(api,owner,w,[b],roles=['ADMIN'])
    assert admin.client.get(PREFIX+f'/workspaces/{w}/brands/{b}').status_code==200
    assert admin.client.get(PREFIX+f'/workspaces/{w}/brands/{hidden}').status_code==404
    admin.client.headers.pop('X-CSRF-Token')
    # Management reads never require CSRF; management writes do.
    assert admin.client.get(PREFIX+f'/workspaces/{w}/memberships').status_code==200
    admin.client.headers['X-CSRF-Token']=admin.response.json()['csrf_token']
    path=PREFIX+f'/workspaces/{w}/memberships/{m["membership_id"]}'
    assert admin.client.patch(path,json={'roles':['OWNER'],'state':'ACTIVE'},headers={'If-Match':'"1"'}).status_code==422
    members=owner.client.get(PREFIX+f'/workspaces/{w}/memberships').json()['items']
    owner_m=next(x for x in members if x['user_id']==owner.response.json()['user']['user_id'])
    assert admin.client.delete(PREFIX+f'/workspaces/{w}/memberships/{owner_m["membership_id"]}',headers={'If-Match':'"1"'}).status_code==409
    reviewer,rm,_=invite(api,owner,w,[b],roles=['REVIEWER','PUBLISHER'])
    for action,status in [('review',200),('publish',200),('edit',403),('connect',403)]:
        assert reviewer.client.post(PREFIX+f'/fixture/workspaces/{w}/brands/{b}/{action}').status_code==status
    grant_path=PREFIX+f'/workspaces/{w}/memberships/{rm["membership_id"]}/brand-grants/{b}'
    assert owner.client.put(grant_path,json={'can_connect_social':True},headers={'If-Match':'"1"'}).status_code==200
    assert reviewer.client.post(PREFIX+f'/fixture/workspaces/{w}/brands/{b}/connect').status_code==200
    edited=owner.client.patch(PREFIX+f'/workspaces/{w}/memberships/{rm["membership_id"]}',json={'roles':['VIEWER'],'state':'ACTIVE'},headers={'If-Match':'"2"'})
    assert edited.status_code==200 and edited.json()['revision']==3,edited.text
    assert reviewer.client.post(PREFIX+f'/fixture/workspaces/{w}/brands/{b}/review').status_code==403
    revoked=owner.client.delete(PREFIX+f'/workspaces/{w}/memberships/{rm["membership_id"]}',headers={'If-Match':'"3"'})
    assert revoked.status_code==200 and revoked.json()['state']=='REVOKED'
    assert reviewer.client.get(PREFIX+f'/workspaces/{w}').status_code==404


def test_invitation_intended_verified_identity_expiry_and_singleuse(api):
    owner=api.login(); w=onboard(api,owner)['workspace_id']; b=brand(owner,w)['brand_id']
    invited=api.login(); stranger=api.login()
    path=PREFIX+f'/workspaces/{w}/invitations'
    r=owner.client.post(path,json={'email':invited.email,'roles':['EDITOR'],'brand_ids':[b]})
    assert r.status_code==201,r.text
    receipt=r.json(); token=receipt['token']; i=receipt['invitation']['invitation_id']
    assert stranger.client.post(PREFIX+'/invitations/accept',json={'token':token}).status_code==403
    with api.db.engine.connect() as conn:
        row=conn.execute(text('SELECT token_hash,expires_at-created_at AS lifetime,state FROM cos_v6.invitations WHERE id=:i'),{'i':UUID(i)}).one()
        assert bytes(row.token_hash)==digest(token)
        assert 604799<row.lifetime.total_seconds()<604801 and row.state=='PENDING'
    accepted=invited.client.post(PREFIX+'/invitations/accept',json={'token':token})
    assert accepted.status_code==200,accepted.text
    assert invited.client.post(PREFIX+'/invitations/accept',json={'token':token}).status_code==422
    with api.db.engine.connect() as conn:
        assert conn.execute(text('SELECT accepted_identity_id IS NOT NULL FROM cos_v6.invitations WHERE id=:i'),{'i':UUID(i)}).scalar_one()
    # Expired local receipt cannot create membership, even with verified intended email.
    r=owner.client.post(path,json={'email':stranger.email,'roles':['VIEWER'],'brand_ids':[b]}).json()
    with api.db.engine.begin() as conn:
        conn.execute(text("UPDATE cos_v6.invitations SET expires_at=clock_timestamp()-interval '1 second' WHERE id=:i"),{'i':UUID(r['invitation']['invitation_id'])})
    assert stranger.client.post(PREFIX+'/invitations/accept',json={'token':r['token']}).status_code==422
    items=owner.client.get(path).json()['items']
    assert any(x['state']=='EXPIRED' for x in items)
    assert all('token' not in x for x in items)


def test_invitation_revoke_authority_and_cross_tenant_brand_rollback(api):
    owner=api.login(); w=onboard(api,owner)['workspace_id']; b=brand(owner,w)['brand_id']
    outsider=api.login(); other=onboard(api,outsider)['workspace_id']; ob=brand(outsider,other)['brand_id']
    body={'email':outsider.email,'roles':['VIEWER'],'brand_ids':[b,ob]}
    with api.db.engine.connect() as c:
        before=c.execute(text('SELECT count(*) FROM cos_v6.invitations WHERE workspace_id=:w'),{'w':UUID(w)}).scalar_one()
    assert owner.client.post(PREFIX+f'/workspaces/{w}/invitations',json=body).status_code==404
    with api.db.engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM cos_v6.invitations WHERE workspace_id=:w'),{'w':UUID(w)}).scalar_one()==before
    r=owner.client.post(PREFIX+f'/workspaces/{w}/invitations',json={**body,'brand_ids':[b]}).json()
    path=PREFIX+f'/workspaces/{w}/invitations/{r["invitation"]["invitation_id"]}'
    assert outsider.client.delete(path,headers={'If-Match':'"1"'}).status_code==404
    assert owner.client.delete(path).status_code==428
    revoked=owner.client.delete(path,headers={'If-Match':'"1"'})
    assert revoked.status_code==200 and revoked.json()['state']=='REVOKED',revoked.text
    assert outsider.client.post(PREFIX+'/invitations/accept',json={'token':r['token']}).status_code==422


def test_expired_and_wrong_subject_onboarding_cannot_create_workspace(api):
    owner=api.login(); attacker=api.login(email=owner.email)
    code=secrets.token_urlsafe(32)
    with api.db.engine.begin() as c:
        c.execute(text('''INSERT INTO cos_v6.onboarding_authorizations(code_hash,intended_issuer,intended_subject,intended_email,expires_at)
              VALUES(:h,:i,:s,:e,clock_timestamp()+interval '1 hour')'''),{'h':digest(code),'i':ISSUER,'s':owner.subject,'e':owner.email})
    r=owner.client.post(PREFIX+'/onboarding/initiate',json={'access_code':code,'email':owner.email})
    body={'challenge_id':r.json()['challenge_id'],'name':'authorized only','timezone':'UTC'}
    assert attacker.client.post(PREFIX+'/workspaces',json=body).status_code==403
    assert owner.client.post(PREFIX+'/workspaces',json=body).status_code==201
    assert owner.client.post(PREFIX+'/workspaces',json=body).status_code==403
