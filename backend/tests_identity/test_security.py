import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from authlib.jose import JsonWebKey, JsonWebToken
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from conftest import PREFIX, COOKIE, ORIGIN, ISSUER, onboard, brand, invite
from secure_api.app import LOGIN_COOKIE, digest, call
from secure_api.audit import audit_identity_privileges


@pytest.mark.parametrize('override', [
    {'iss':'https://attacker.invalid'}, {'aud':'other-client'}, {'aud':['fixture-client','other']},
    {'azp':'other-client'}, {'sub':''}, {'sub':None}, {'exp':1}, {'iat':4102444800},
    {'nonce':'bad'}, {'email_verified':False}, {'email_verified':'true'}, {'exp':True},
])
def test_signed_id_token_claim_failures_never_create_session(api, override):
    with api.db.engine.connect() as c:
        before = c.execute(text('SELECT count(*) FROM cos_v6.sessions')).scalar_one()
    login=api.login(overrides=override)
    assert login.response.status_code==401
    assert login.response.json()['code']=='INVALID_LOGIN'
    with api.db.engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM cos_v6.sessions')).scalar_one()==before
    # Failed verification consumes state durably, so no second network exchange.
    count=len(api.fake.requests)
    replay=login.client.get(PREFIX+'/auth/callback',params={'state':login.state,'code':login.code})
    assert replay.status_code==401 and len(api.fake.requests)==count


@pytest.mark.parametrize('attack',['bad_signature','unknown_kid','duplicate_kid','jku','x5u','embedded_jwk','hmac','none','weak_rsa'])
def test_jwks_algorithm_and_key_selection_defenses(api,attack):
    header={'alg':'RS256','kid':'fixture-key'}
    if attack=='bad_signature':
        api.fake.signing_key=JsonWebKey.generate_key('RSA',2048,is_private=True)
    elif attack=='unknown_kid':
        header['kid']='unknown'
        private=api.fake.key.as_dict(is_private=True)
        private['kid']='unknown'
        api.fake.signing_key=JsonWebKey.import_key(private)
    elif attack=='duplicate_kid':
        k=api.fake.key.as_dict(is_private=False)
        api.fake.jwks_override={'keys':[k,k]}
    elif attack in ('jku','x5u'):
        header[attack]='https://attacker.invalid/keys'
    elif attack=='embedded_jwk':
        header['jwk']=api.fake.key.as_dict(is_private=False)
    elif attack=='hmac':
        api.fake.raw_token=JsonWebToken(['HS256']).encode({'alg':'HS256','kid':'fixture-key'},{'sub':'attacker'},b'a'*32).decode()
    elif attack=='none':
        api.fake.raw_token='eyJhbGciOiJub25lIn0.eyJzdWIiOiJhdHRhY2tlciJ9.'
    elif attack=='weak_rsa':
        api.fake.key=JsonWebKey.generate_key('RSA',1024,is_private=True,options={'kid':'fixture-key'})
    result=api.login(header=header)
    assert result.response.status_code==401
    assert all(path in ('/token','/jwks') for _,path in api.fake.requests)


def test_state_browser_binding_singleuse_and_login_rate_limit(api):
    c=api.client()
    start=c.post(PREFIX+'/auth/login',json={'return_path':'/library'})
    code,state=api.fake.issue(start.json()['authorization_url'],'fixture-state','state@fixture.invalid')
    thief=api.client()
    wrong=thief.get(PREFIX+'/auth/callback',params={'code':code,'state':state})
    assert wrong.status_code==401 and api.fake.requests==[]
    incorrect=c.get(PREFIX+'/auth/callback',params={'code':code,'state':secrets.token_urlsafe(32)})
    assert incorrect.status_code==401 and api.fake.requests==[]
    good=c.get(PREFIX+'/auth/callback',params={'code':code,'state':state})
    assert good.status_code==200
    # Restore consumed browser cookie to exercise DB replay, not just cookie absence.
    old_browser=start.cookies.get(LOGIN_COOKIE)
    c.cookies.set(LOGIN_COOKIE,old_browser,domain='app.fixture.invalid',path='/')
    count=len(api.fake.requests)
    assert c.get(PREFIX+'/auth/callback',params={'code':code,'state':state}).status_code==401
    assert len(api.fake.requests)==count
    with api.db.engine.begin() as conn:
        conn.execute(text("UPDATE cos_v6.login_transactions SET created_at=created_at-interval '2 minutes'"))
    for _ in range(10):
        assert c.post(PREFIX+'/auth/login',json={'return_path':'/'}).status_code==200
    limited=c.post(PREFIX+'/auth/login',json={'return_path':'/'})
    assert limited.status_code==429 and limited.headers['Retry-After']=='60'


def test_expired_login_transaction_rejected_before_network(api):
    c=api.client()
    r=c.post(PREFIX+'/auth/login',json={'return_path':'/'})
    code,state=api.fake.issue(r.json()['authorization_url'],'expired-login','expire@fixture.invalid')
    with api.db.engine.begin() as conn:
        conn.execute(text("UPDATE cos_v6.login_transactions SET expires_at=clock_timestamp()-interval '1 second' WHERE state_hash=:h"),{'h':digest(state)})
    assert c.get(PREFIX+'/auth/callback',params={'code':code,'state':state}).status_code==401
    assert api.fake.requests==[]


def test_no_email_identity_linking_same_subject_reuses_identity(api):
    email='same-'+uuid4().hex+'@fixture.invalid'
    a=api.login(email=email)
    b=api.login(email=email)
    a2=api.login(subject=a.subject,email=email)
    assert a.response.status_code==b.response.status_code==a2.response.status_code==200
    assert a.response.json()['user']['user_id']!=b.response.json()['user']['user_id']
    assert a.response.json()['user']['user_id']==a2.response.json()['user']['user_id']
    assert a.client.cookies.get(COOKIE)!=a2.client.cookies.get(COOKIE)


@pytest.mark.parametrize('attack',['no_csrf','bad_csrf','no_origin','foreign_origin','null_origin'])
def test_cookie_samesite_is_not_csrf(api,attack):
    user=api.login()
    token=user.client.cookies.get(COOKIE)
    if attack=='no_csrf': user.client.headers.pop('X-CSRF-Token')
    if attack=='bad_csrf': user.client.headers['X-CSRF-Token']='invalid'
    if attack=='no_origin': user.client.headers.pop('Origin')
    if attack=='foreign_origin': user.client.headers['Origin']='https://evil.invalid'
    if attack=='null_origin': user.client.headers['Origin']='null'
    result=user.client.post(PREFIX+'/auth/logout')
    assert result.status_code==403
    with api.db.engine.connect() as c:
        assert c.execute(text('SELECT revoked_at FROM cos_v6.sessions WHERE token_hash=:h'),{'h':digest(token)}).scalar_one() is None


def test_logout_session_expiry_and_pooled_actor_reset(api):
    user=api.login()
    token=user.client.cookies.get(COOKIE)
    csrf=user.response.json()['csrf_token']
    with api.db.runtime.begin() as c:
        call(c,'api_bind',token=token,csrf=csrf,writing=False)
        assert call(c,'api_actor')==UUID(user.response.json()['user']['user_id'])
        pid=c.execute(text('SELECT pg_backend_pid()')).scalar_one()
    with api.db.runtime.begin() as c:
        assert c.execute(text('SELECT pg_backend_pid()')).scalar_one()==pid
        assert call(c,'api_actor') is None
        # Arbitrary UUID GUCs cannot establish an actor, nor can a session row UUID.
        c.execute(text("SELECT set_config('cos.actor_id',:u,true),set_config('app.user_id',:u,true),set_config('cos.api_token',:u,true)"),{'u':user.response.json()['user']['user_id']})
        assert call(c,'api_actor') is None
    assert user.client.post(PREFIX+'/auth/logout').status_code==200
    user.client.cookies.set(COOKIE,token,domain='app.fixture.invalid',path='/')
    assert user.client.get(PREFIX+'/auth/session').status_code==401
    second=api.login()
    with api.db.engine.begin() as c:
        c.execute(text("UPDATE cos_v6.sessions SET created_at=clock_timestamp()-interval '10 hours',expires_at=clock_timestamp()-interval '1 second' WHERE token_hash=:h"),{'h':digest(second.client.cookies.get(COOKIE))})
    assert second.client.get(PREFIX+'/users/me').status_code==401


@pytest.mark.parametrize('isolation',['REPEATABLE READ','SERIALIZABLE'])
def test_unsupported_transaction_snapshot_rejected(api,isolation):
    user=api.login()
    with api.db.runtime.connect().execution_options(isolation_level=isolation) as c:
        with pytest.raises(DBAPIError,match='READ_COMMITTED_REQUIRED'):
            call(c,'api_bind',token=user.client.cookies.get(COOKIE),csrf='',writing=False)
        c.rollback()


def test_no_direct_sensitive_dml_or_cross_role_impersonation(api):
    user=api.login()
    w=onboard(api,user)['workspace_id']
    with api.db.runtime.begin() as c:
        call(c,'api_bind',token=user.client.cookies.get(COOKIE),csrf='',writing=False)
        assert call(c,'api_actor')
    for engine,sql in [
        (api.db.runtime,'SELECT * FROM cos_v6.sessions'),
        (api.db.runtime,'SELECT * FROM cos_v6.login_transactions'),
        (api.db.runtime,"UPDATE cos_v6.workspace_memberships SET roles=ARRAY['admin']"),
        (api.db.runtime,'SELECT cos_v6.auth_consume(NULL,NULL)'),
        (api.db.runtime,'SELECT cos_v6.api_workspace_json(NULL)'),
        (api.db.runtime,'SELECT cos_v6.actor()'),
        (api.db.runtime,'SET ROLE cos_identity_auth'),
        (api.db.runtime,'SET ROLE cos_identity_owner'),
        (api.db.auth,"SELECT cos_v6.api_create_workspace(NULL,'bad','UTC')"),
        (api.db.auth,'SELECT * FROM cos_v6.workspace_memberships'),
    ]:
        with engine.begin() as c:
            with pytest.raises(DBAPIError): c.execute(text(sql))
            c.rollback()
    # A valid opaque token but missing CSRF cannot call mutation procedures either.
    with api.db.runtime.begin() as c:
        call(c,'api_bind',token=user.client.cookies.get(COOKIE),csrf='',writing=False)
        with pytest.raises(DBAPIError,match='CSRF_INVALID'):
            call(c,'api_authorize',w=UUID(w),b=None,a='manage')
        c.rollback()


def test_session_revoke_race_serializes_and_next_request_denied(api):
    user=api.login()
    token=user.client.cookies.get(COOKIE)
    started,finished=Event(),Event()
    with api.db.runtime.connect() as c:
        txn=c.begin()
        call(c,'api_bind',token=token,csrf='',writing=False)
        def revoke():
            with api.db.engine.begin() as admin:
                started.set()
                admin.execute(text('UPDATE cos_v6.sessions SET revoked_at=clock_timestamp() WHERE token_hash=:h'),{'h':digest(token)})
            finished.set()
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(revoke)
            assert started.wait(3)
            assert not finished.wait(.15), 'revocation must wait on in-flight session SHARE lock'
            txn.commit()
            future.result(timeout=3)
    assert user.client.get(PREFIX+'/auth/session').status_code==401


def test_committed_grant_revocation_wins_over_old_snapshot(api):
    owner=api.login(); w=onboard(api,owner)['workspace_id']; b=brand(owner,w)['brand_id']
    editor,member,_=invite(api,owner,w,[b])
    with api.db.runtime.connect() as old:
        old.begin()
        call(old,'api_bind',token=editor.client.cookies.get(COOKIE),csrf=editor.response.json()['csrf_token'],writing=True)
        old.execute(text('SELECT txid_current_snapshot()'))
        r=owner.client.delete(PREFIX+f'/workspaces/{w}/memberships/{member["membership_id"]}/brand-grants/{b}',headers={'If-Match':'"1"'})
        assert r.status_code==200,r.text
        with pytest.raises(DBAPIError,match='NOT_FOUND'):
            call(old,'api_authorize',w=UUID(w),b=UUID(b),a='edit')
        old.rollback()
    assert editor.client.get(PREFIX+f'/workspaces/{w}/brands/{b}').status_code==404


@pytest.mark.parametrize('drift',['public_function','runtime_function','auth_dml','runtime_column','rls_disabled','role_super'])
def test_privilege_audit_rejects_drift(db,drift):
    with db.engine.connect() as c:
        tx=c.begin()
        if drift=='public_function':
            c.exec_driver_sql('CREATE FUNCTION cos_v6.identity_unsafe() RETURNS int LANGUAGE sql AS $$SELECT 1$$')
        elif drift=='runtime_function':
            c.exec_driver_sql('GRANT EXECUTE ON FUNCTION cos_v6.auth_consume(bytea,bytea) TO cos_api_runtime')
        elif drift=='auth_dml':
            c.exec_driver_sql('GRANT UPDATE ON cos_v6.workspace_memberships TO cos_identity_auth')
        elif drift=='runtime_column':
            c.exec_driver_sql('GRANT UPDATE(roles) ON cos_v6.workspace_memberships TO cos_api_runtime')
        elif drift=='rls_disabled':
            c.exec_driver_sql('ALTER TABLE cos_v6.sessions NO FORCE ROW LEVEL SECURITY')
        else:
            c.exec_driver_sql('ALTER ROLE cos_api_runtime SUPERUSER')
        with pytest.raises(RuntimeError,match='Identity privilege audit failed'):
            audit_identity_privileges(c)
        tx.rollback()
