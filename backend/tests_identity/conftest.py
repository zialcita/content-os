"""Only fixture accounts, fake signed IdP transport and a fresh real PostgreSQL."""
import base64
import json
import os
import secrets
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
import hashlib

import httpx
import pytest
from alembic import command
from alembic.config import Config
from authlib.jose import JsonWebKey, JsonWebToken
from cryptography.fernet import Fernet
from fastapi import APIRouter, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from secure_api.app import Settings, create_app, PREFIX, COOKIE, digest, call
from secure_api.oidc import OIDCConfig
from secure_api.dependencies import get_scope
from secure_api.audit import audit_identity_privileges
from foundation.privileges import audit_function_privileges

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'docs/evidence/m1/identity'
ORIGIN = 'https://app.fixture.invalid'
ISSUER = 'https://idp.fixture.invalid'


def migrate(c):
    config = Config(str(ROOT / 'backend/alembic.ini'))
    config.attributes['connection'] = c
    command.upgrade(config, 'identity@head')


@pytest.fixture(scope='session')
def db():
    manifest = Path(os.environ['IDENTITY_DISPOSABLE_MANIFEST'])
    data = json.loads(manifest.read_text())
    temp = Path(data['root']).resolve()
    assert temp.name.startswith('contentos-identity-pg-') and manifest.resolve().parent == temp
    url = make_url(data['dsn'])
    host = url.query.get('host', url.host)
    assert host and Path(host).resolve().is_relative_to(temp)
    assert 'DATABASE_URL' not in os.environ
    engine = create_engine(url, hide_parameters=True)
    with engine.begin() as c:
        c.execute(text('CREATE TABLE public.identity_legacy_sentinel(id text PRIMARY KEY,payload text)'))
        c.execute(text("INSERT INTO public.identity_legacy_sentinel VALUES('legacy/raw','unchanged')"))
        defaults = c.execute(text('SELECT oid,defaclacl::text FROM pg_default_acl ORDER BY oid')).all()
        migrate(c)
        audit_identity_privileges(c)
        audit_function_privileges(c)
        assert defaults == c.execute(text('SELECT oid,defaclacl::text FROM pg_default_acl ORDER BY oid')).all()
        c.exec_driver_sql('CREATE ROLE fixture_api_service LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS')
        c.exec_driver_sql('CREATE ROLE fixture_auth_service LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS')
        c.exec_driver_sql('GRANT cos_api_runtime TO fixture_api_service')
        c.exec_driver_sql('GRANT cos_identity_auth TO fixture_auth_service')
    runtime = create_engine(url.set(username='fixture_api_service'), hide_parameters=True, pool_size=1, max_overflow=2)
    auth = create_engine(url.set(username='fixture_auth_service'), hide_parameters=True, pool_size=1)
    with engine.connect() as c:
        server = c.execute(text('SELECT version()')).scalar_one()
        assert 'PostgreSQL 16.2' in server
        env = {'server': server, 'schema_revision': '0002_sessions', 'real_oidc_proof': False,
               'identity_source': 'cryptographically signed fake IdP, fixture accounts only',
               'provider_calls': 0, 'database_accounts': 'two service fixture logins, NOT per-user',
               'env_scrubbed': True, 'dsn_logged': False,
               'versions': {n: __import__('importlib.metadata', fromlist=['version']).version(n)
                            for n in ('Authlib', 'cryptography', 'fastapi', 'sqlalchemy', 'psycopg', 'httpx', 'pytest')}}
        (EVIDENCE / 'environment.json').write_text(json.dumps(env, indent=2))
    yield SimpleNamespace(engine=engine, runtime=runtime, auth=auth)
    runtime.dispose(); auth.dispose(); engine.dispose()


class FakeIdP:
    """Cryptographic fixture, NOT an authorization-server/provider certification."""
    def __init__(self):
        self.key = JsonWebKey.generate_key('RSA', 2048, is_private=True, options={'kid': 'fixture-key'})
        self.codes, self.requests = {}, []
        self.jwks_override = None
        self.signing_key = None
        self.raw_token = None

    def issue(self, authorization_url, subject, email, overrides=None, header=None):
        q = parse_qs(urlsplit(authorization_url).query)
        assert q['response_type'] == ['code'] and q['code_challenge_method'] == ['S256']
        assert q['client_id'] == ['fixture-client']
        assert q['redirect_uri'] == [ORIGIN + PREFIX + '/auth/callback']
        claims = {'iss': ISSUER, 'sub': subject, 'aud': 'fixture-client', 'exp': int(time.time())+300,
                  'iat': int(time.time()), 'nonce': q['nonce'][0], 'email': email, 'email_verified': True,
                  'name': 'FIXTURE ACCOUNT — not real OIDC proof'}
        claims.update(overrides or {})
        code = secrets.token_urlsafe(24)
        self.codes[code] = (claims, q['code_challenge'][0], header or {'alg': 'RS256', 'kid': 'fixture-key'})
        return code, q['state'][0]

    def handler(self, request):
        self.requests.append((request.method, request.url.path))
        assert request.url.host == 'idp.fixture.invalid', 'No real provider access permitted'
        if request.url.path == '/token':
            p = parse_qs(request.content.decode())
            row = self.codes.pop(p['code'][0], None)
            if row is None:
                return httpx.Response(400, json={'error': 'invalid_grant'})
            claims, challenge, header = row
            assert base64.urlsafe_b64encode(hashlib.sha256(p['code_verifier'][0].encode()).digest()).decode().rstrip('=') == challenge
            assert p['grant_type'] == ['authorization_code']
            token = self.raw_token or JsonWebToken(['RS256']).encode(header, claims, self.signing_key or self.key).decode()
            return httpx.Response(200, json={'token_type': 'Bearer', 'access_token': 'fixture-access-token-never-persist', 'id_token': token, 'expires_in': 300})
        if request.url.path == '/jwks':
            return httpx.Response(200, json=self.jwks_override or {'keys': [self.key.as_dict(is_private=False)]})
        raise AssertionError('Unexpected provider route')


@pytest.fixture
def api(db):
    fake = FakeIdP()
    settings = Settings(origin=ORIGIN,
        oidc=OIDCConfig(ISSUER, 'fixture-client', ISSUER+'/authorize', ISSUER+'/token', ISSUER+'/jwks', ORIGIN+PREFIX+'/auth/callback'),
        state_encryption_key=Fernet.generate_key(), csrf_key=secrets.token_bytes(32), cursor_key=secrets.token_bytes(32), mode='development')
    feature = APIRouter()

    @feature.get(PREFIX+'/fixture/workspaces/{workspace_id}/brands/{brand_id}')
    def scoped_read(workspace_id: __import__('uuid').UUID, brand_id: __import__('uuid').UUID, request: Request):
        s = get_scope(request, workspace_id, brand_id)
        return {'user_id': str(s.user_id), 'membership_id': str(s.membership_id),
                'rows': len(s.connection.execute(text('SELECT id FROM cos_v6.brands')).all())}

    @feature.post(PREFIX+'/fixture/workspaces/{workspace_id}/brands/{brand_id}/{action}')
    def scoped_write(workspace_id: __import__('uuid').UUID, brand_id: __import__('uuid').UUID, action: str, request: Request):
        s = get_scope(request, workspace_id, brand_id, action)
        return {'membership_id': str(s.membership_id)}

    app = create_app(settings, db.runtime, db.auth, oidc_transport=httpx.MockTransport(fake.handler), feature_routers=[feature])
    clients = []

    def client():
        c = TestClient(app, base_url=ORIGIN, raise_server_exceptions=False)
        c.headers['Origin'] = ORIGIN
        clients.append(c)
        return c

    def login(c=None, subject=None, email=None, overrides=None, header=None):
        c = c or client()
        subject = subject or 'fixture-' + uuid4().hex
        email = email or subject + '@fixture.invalid'
        # All TestClients share one fixture IP. Age prior successful fixture rows;
        # production code retains its database-backed per-IP rate limit.
        with db.engine.begin() as conn:
            conn.execute(text("UPDATE cos_v6.login_transactions SET created_at=created_at-interval '2 minutes' WHERE finalized_at IS NOT NULL"))
        start = c.post(PREFIX+'/auth/login', json={'return_path': '/library'})
        assert start.status_code == 200, start.text
        code, state = fake.issue(start.json()['authorization_url'], subject, email, overrides, header)
        result = c.get(PREFIX+'/auth/callback', params={'code': code, 'state': state})
        if result.status_code == 200:
            c.headers['X-CSRF-Token'] = result.json()['csrf_token']
        return SimpleNamespace(client=c, response=result, subject=subject, email=email, state=state, code=code)

    yield SimpleNamespace(app=app, db=db, settings=settings, fake=fake, client=client, login=login)
    for c in clients:
        c.close()
    # Isolate rate limits across tests without weakening deployed checks.
    with db.engine.begin() as c:
        c.execute(text("UPDATE cos_v6.login_transactions SET created_at=created_at-interval '2 minutes'"))


def onboard(api, login, name='FIXTURE workspace'):
    assert login.response.status_code == 200, login.response.text
    code = secrets.token_urlsafe(32)
    with api.db.engine.begin() as c:
        c.execute(text('''INSERT INTO cos_v6.onboarding_authorizations(code_hash,intended_issuer,intended_subject,intended_email,expires_at)
              VALUES(:h,:i,:s,:e,clock_timestamp()+interval '1 hour')'''),
              {'h': digest(code), 'i': ISSUER, 's': login.subject, 'e': login.email})
    challenge = login.client.post(PREFIX+'/onboarding/initiate', json={'access_code': code, 'email': login.email})
    assert challenge.status_code == 200, challenge.text
    result = login.client.post(PREFIX+'/workspaces', json={'challenge_id': challenge.json()['challenge_id'], 'name': name, 'timezone': 'UTC'})
    assert result.status_code == 201, result.text
    return result.json()


def brand(login, w, name='FIXTURE brand'):
    r = login.client.post(PREFIX+f'/workspaces/{w}/brands', json={'name': name, 'timezone': 'UTC'}, headers={'Idempotency-Key': str(uuid4())})
    assert r.status_code == 201, r.text
    return r.json()


def invite(api, owner, w, brands, roles=('EDITOR',), invitee=None):
    invitee = invitee or api.login()
    assert invitee.response.status_code == 200, invitee.response.text
    r = owner.client.post(PREFIX+f'/workspaces/{w}/invitations', json={'email': invitee.email, 'roles': list(roles), 'brand_ids': brands})
    assert r.status_code == 201, r.text
    receipt = r.json()
    assert receipt['delivery'] == 'LOCAL_RECEIPT_NOT_SENT'
    accepted = invitee.client.post(PREFIX+'/invitations/accept', json={'token': receipt['token']})
    assert accepted.status_code == 200, accepted.text
    return invitee, accepted.json(), receipt
