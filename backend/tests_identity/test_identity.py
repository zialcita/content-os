import json
import secrets
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from conftest import PREFIX, COOKIE, ORIGIN, ISSUER, EVIDENCE, onboard, brand, invite, migrate
from secure_api.app import create_app, call, digest, LOGIN_COOKIE
from secure_api.audit import audit_identity_privileges
from foundation.privileges import audit_function_privileges


def test_signed_fake_oidc_real_session_no_tokens_stored(api):
    login = api.login()
    assert login.response.status_code == 200, login.response.text
    payload = login.response.json()
    assert payload['user']['display_name'].startswith('FIXTURE ACCOUNT')
    assert payload['active_workspace_id'] is None
    assert payload['expires_at'].endswith('Z')
    session_token = login.client.cookies.get(COOKIE)
    assert len(session_token) >= 43 and session_token.count('.') == 0
    cookies = login.response.headers.get_list('set-cookie')
    assert any(COOKIE in c and 'HttpOnly' in c and 'Secure' in c and 'SameSite=lax' in c and 'Path=/' in c for c in cookies)
    assert login.client.get(PREFIX+'/users/me').json() == payload['user']
    assert login.client.get(PREFIX+'/auth/session').json()['csrf_token'] == payload['csrf_token']
    with api.db.engine.connect() as c:
        s = c.execute(text('SELECT token_hash,csrf_secret_hash FROM cos_v6.sessions WHERE user_id=:u'), {'u': UUID(payload['user']['user_id'])}).one()
        assert bytes(s.token_hash) == digest(session_token)
        assert bytes(s.csrf_secret_hash) == digest(payload['csrf_token'])
        assert c.execute(text("SELECT count(*) FROM cos_v6.workspace_memberships WHERE user_id=:u"), {'u': UUID(payload['user']['user_id'])}).scalar_one() == 0
        assert c.execute(text("SELECT count(*) FROM cos_v6.login_transactions WHERE finalized_at IS NOT NULL AND verifier_ciphertext<>''")).scalar_one() == 0
    assert api.fake.requests == [('POST','/token'), ('GET','/jwks')]


def test_real_asgi_workspaces_brands_and_role_denials(api):
    owner = api.login()
    w = onboard(api, owner)['workspace_id']
    b, hidden = brand(owner,w)['brand_id'], brand(owner,w)['brand_id']
    other = api.login()
    ow = onboard(api, other)['workspace_id']
    ob = brand(other,ow)['brand_id']
    editor, member, _ = invite(api, owner, w, [b])
    assert editor.client.get(PREFIX+f'/workspaces/{w}/brands').json()['items'][0]['brand_id'] == b
    assert len(editor.client.get(PREFIX+f'/workspaces/{w}/brands').json()['items']) == 1
    assert editor.client.get(PREFIX+f'/workspaces/{w}/brands/{hidden}').status_code == 404
    assert editor.client.get(PREFIX+f'/workspaces/{ow}').status_code == 404
    assert editor.client.get(PREFIX+f'/workspaces/{w}/brands/{ob}').status_code == 404
    assert editor.client.get(PREFIX+f'/workspaces/{ow}/brands/{ob}').status_code == 404
    assert editor.client.get(PREFIX+f'/workspaces/{w}/memberships').status_code == 403
    read = editor.client.get(PREFIX+f'/fixture/workspaces/{w}/brands/{b}')
    assert read.status_code == 200 and read.json()['membership_id'] == member['membership_id']
    assert read.json()['rows'] == 1
    for action, expected in [('edit',200),('review',403),('publish',403),('connect',403),('invented',403)]:
        assert editor.client.post(PREFIX+f'/fixture/workspaces/{w}/brands/{b}/{action}').status_code == expected
    # One global user can legitimately join two workspaces without an email link.
    _, _, _ = invite(api, other, ow, [ob], invitee=editor)
    listed = editor.client.get(PREFIX+'/workspaces').json()['items']
    assert {i['workspace_id'] for i in listed} == {w,ow}
    assert editor.client.post(PREFIX+'/auth/workspace', json={'workspace_id': ow}).json()['active_workspace_id'] == ow


def test_onboarding_requires_explicit_authorization_never_email_owner(api):
    user = api.login()
    denied = user.client.post(PREFIX+'/workspaces', json={'challenge_id':str(uuid4()), 'name':'blocked','timezone':'UTC'})
    assert denied.status_code == 403
    denied = user.client.post(PREFIX+'/workspaces', json={'owner_email':user.email,'name':'blocked','timezone':'UTC'})
    assert denied.status_code == 422 and denied.json()['code'] == 'VALIDATION_ERROR'
    with api.db.engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM cos_v6.workspace_memberships WHERE user_id=:u'),{'u':UUID(user.response.json()['user']['user_id'])}).scalar_one()==0
    onboard(api,user)


def test_schema_audit_and_migration_preservation(db):
    with db.engine.begin() as c:
        migrate(c)
        audit_identity_privileges(c)
        audit_function_privileges(c)
        assert c.execute(text('SELECT payload FROM public.identity_legacy_sentinel')).scalar_one()=='unchanged'
        assert c.execute(text('SELECT count(*) FROM cos_v6.database_principals')).scalar_one()==0


def test_production_always_refuses(api):
    with pytest.raises(RuntimeError,match='Production refused'):
        create_app(replace(api.settings,mode='production'),api.db.runtime,api.db.auth)
    with pytest.raises(RuntimeError,match='minimally privileged'):
        create_app(api.settings,api.db.engine,api.db.auth)
    with api.db.engine.begin() as c:
        c.exec_driver_sql('GRANT EXECUTE ON FUNCTION cos_v6.auth_consume(bytea,bytea) TO fixture_api_service')
    try:
        with pytest.raises(RuntimeError,match='Effective service privilege'):
            create_app(api.settings,api.db.runtime,api.db.auth)
    finally:
        with api.db.engine.begin() as c:
            c.exec_driver_sql('REVOKE EXECUTE ON FUNCTION cos_v6.auth_consume(bytea,bytea) FROM fixture_api_service')


def test_openapi_is_generated_runtime_subset(api):
    r=api.client().get(PREFIX+'/openapi.json')
    assert r.status_code==200
    schema=r.json()
    assert '/api/v6/auth/session' in schema['paths']
    assert not any('/v1/' in p for p in schema['paths'])
    assert not any('voice-preview' in p for p in schema['paths'])
    # Fixture scope routes are test-only, never part of the production module.
    schema['paths']={p:v for p,v in schema['paths'].items() if '/fixture/' not in p}
    (EVIDENCE/'runtime.openapi.json').write_text(json.dumps(schema,indent=2))
