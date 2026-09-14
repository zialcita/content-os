"""Direct-review regressions; all IdP data and account identities are fixtures."""
import asyncio
import gzip
import secrets
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from conftest import PREFIX, ORIGIN, COOKIE, onboard, brand, migrate
from secure_api.app import create_app, digest, call
from secure_api.errors import APIError
from secure_api.oidc import OIDCVerifier


@pytest.mark.parametrize('override', [
    {'exp': float('nan')}, {'exp': float('inf')}, {'iat': float('nan')},
    {'iat': float('-inf')}, {'iat': 4102444800, 'exp': 4102444700},
])
def test_nonfinite_and_invalid_lifetimes_cannot_create_session(api, override):
    with api.db.engine.connect() as c:
        before = c.execute(text('SELECT count(*) FROM cos_v6.sessions')).scalar_one()
    result = api.login(overrides=override).response
    assert result.status_code == 401 and result.json()['code'] == 'INVALID_LOGIN'
    with api.db.engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM cos_v6.sessions')).scalar_one() == before


@pytest.mark.parametrize('host', ['attacker.invalid', 'app.fixture.invalid:444'])
def test_exact_host_is_checked_even_on_anonymous_endpoints(api, host):
    response = api.client().post(PREFIX+'/auth/login', json={'return_path':'/'}, headers={'Host':host})
    assert response.status_code == 403
    assert response.json()['code'] == 'ORIGIN_INVALID'


def test_invitation_listing_exposes_revision_for_safe_revoke(api):
    owner = api.login()
    w = onboard(api, owner)['workspace_id']
    b = brand(owner, w)['brand_id']
    created = owner.client.post(PREFIX+f'/workspaces/{w}/invitations',
        json={'email':'pending@fixture.invalid','roles':['EDITOR'],'brand_ids':[b]})
    assert created.status_code == 201
    invitation = created.json()['invitation']
    listing = owner.client.get(PREFIX+f'/workspaces/{w}/invitations').json()['items']
    selected = next(i for i in listing if i['invitation_id'] == invitation['invitation_id'])
    assert selected['revision'] == 1
    response = owner.client.delete(PREFIX+f'/workspaces/{w}/invitations/'+selected['invitation_id'],
                                   headers={'If-Match':'"1"'})
    assert response.status_code == 200
    assert response.json()['revision'] == 2 and response.headers['ETag'] == '"2"'


def test_database_io_does_not_run_on_the_asgi_event_loop(api):
    observed = []
    def before_execute(*args):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            observed.append('worker')
        else:
            observed.append('event_loop')
    for engine in (api.db.runtime, api.db.auth):
        event.listen(engine, 'before_cursor_execute', before_execute)
    try:
        login = api.login()
        assert login.response.status_code == 200
        assert login.client.get(PREFIX+'/auth/session').status_code == 200
        assert login.client.post(PREFIX+'/auth/logout').status_code == 200
    finally:
        for engine in (api.db.runtime, api.db.auth):
            event.remove(engine, 'before_cursor_execute', before_execute)
    assert observed and set(observed) == {'worker'}


def test_concurrent_session_mutations_do_not_deadlock(api):
    login = api.login()
    w = onboard(api, login)['workspace_id']
    token, csrf = login.client.cookies.get(COOKIE), login.response.json()['csrf_token']
    barrier = Barrier(2)
    def switch(_):
        with TestClient(api.app, base_url=ORIGIN, raise_server_exceptions=False) as client:
            headers={'Origin':ORIGIN, 'Cookie':COOKIE+'='+token, 'X-CSRF-Token':csrf}
            barrier.wait(timeout=5)
            return client.post(PREFIX+'/auth/workspace', json={'workspace_id':w}, headers=headers).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(switch, range(2))) == [200, 200]


def test_head_rerun_audits_identity_role_drift(api):
    with pytest.raises(RuntimeError, match='Identity privilege audit failed'):
        with api.db.engine.begin() as c:
            c.exec_driver_sql('GRANT SELECT ON cos_v6.sessions TO cos_api_runtime')
            migrate(c)
    # The failed validation transaction rolls back the injected grant.
    with api.db.runtime.connect() as c:
        assert not c.execute(text("SELECT has_table_privilege(current_user,'cos_v6.sessions','SELECT')")).scalar_one()


def test_identity_revision_preserves_prior_history_and_audits(api):
    from alembic import command
    from alembic.config import Config
    from conftest import ROOT
    from foundation.migration_audit import audit_migrated_privileges
    with api.db.engine.begin() as c:
        before = c.execute(text('SELECT count(*) FROM cos_v6.sessions')).scalar_one()
        config=Config(str(ROOT/'backend/alembic.ini'))
        config.attributes['connection']=c
        # This suite certifies002; the content-core suite exercises combined head003.
        command.upgrade(config, '0002_sessions')
        audit_migrated_privileges(c)
        assert c.execute(text('SELECT version_num FROM public.cos_v6_alembic_version')).scalar_one() == '0002_sessions'
        assert c.execute(text('SELECT payload FROM public.identity_legacy_sentinel')).scalar_one() == 'unchanged'
        assert c.execute(text('SELECT count(*) FROM cos_v6.sessions')).scalar_one() == before


def test_null_sql_page_limit_is_rejected(api):
    login=api.login()
    with pytest.raises(DBAPIError, match='INVALID_INPUT'):
        with api.db.runtime.begin() as c:
            call(c,'api_bind',token=login.client.cookies.get(COOKIE),csrf='',writing=False)
            call(c,'api_list',kind='workspace',w=None,target=None,after_time=None,after_id=None,n=None)


class LargeResponse(httpx.AsyncByteStream):
    def __init__(self):
        self.yielded=0
    async def __aiter__(self):
        for _ in range(1024):
            self.yielded+=1
            yield b'x'*4096


def test_token_response_is_bounded_before_authlib_parsing(api):
    body=LargeResponse()
    def handler(request):
        assert request.headers['Accept-Encoding'] == 'identity'
        return httpx.Response(200,stream=body,headers={'Content-Type':'application/json'})
    verifier=OIDCVerifier(api.settings.oidc,httpx.MockTransport(handler))
    with pytest.raises(APIError,match='INVALID_LOGIN'):
        asyncio.run(verifier.complete('fixture-code','fixture-pkce','fixture-nonce'))
    assert body.yielded <= 33  # stop once the 128KiB bound is crossed, not after 4MiB


def test_compressed_token_response_is_refused(api):
    def handler(request):
        return httpx.Response(200,content=gzip.compress(b'x'*1000000),
                              headers={'Content-Encoding':'gzip','Content-Type':'application/json'})
    verifier=OIDCVerifier(api.settings.oidc,httpx.MockTransport(handler))
    with pytest.raises(APIError,match='INVALID_LOGIN'):
        asyncio.run(verifier.complete('fixture-code','fixture-pkce','fixture-nonce'))
