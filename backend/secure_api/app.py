"""Separate secure factory; legacy main and provider adapters are never imported."""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from uuid import UUID, uuid4
from urllib.parse import urlsplit
import base64
import hmac
import json
import secrets

from cryptography.fernet import Fernet
from fastapi import FastAPI, Request, Response, APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from starlette.concurrency import run_in_threadpool

from . import models as M
from .dependencies import get_scope, connection
from .errors import APIError, ErrorEnvelope, STATUS, install_errors, response as error_response
from .oidc import OIDCConfig, OIDCVerifier

COOKIE = '__Host-contentos-session'
LOGIN_COOKIE = '__Host-contentos-login'
PREFIX = '/api/v6'


def digest(value):
    return sha256(value.encode('utf8')).digest()


def call(c, name, **params):
    # Function names are source constants, not user supplied.
    return c.execute(text('SELECT cos_v6.' + name + '(' + ','.join(':' + k for k in params) + ')'), params).scalar_one()


@dataclass(frozen=True)
class Settings:
    origin: str
    oidc: OIDCConfig
    state_encryption_key: bytes
    csrf_key: bytes
    cursor_key: bytes
    mode: str

    def validate(self):
        if self.mode != 'development':
            raise RuntimeError('Production refused: identity/feature integration, deployment and external gates are not proven')
        parsed = urlsplit(self.origin)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('Exact HTTPS origin required')
        if self.oidc.redirect_uri != self.origin + PREFIX + '/auth/callback':
            raise ValueError('OIDC callback must be the exact secure API callback URL')
        if min(len(self.csrf_key), len(self.cursor_key)) < 32:
            raise ValueError('Independent 256-bit server keys required')
        Fernet(self.state_encryption_key)


def _engine_guard(engine, group):
    with engine.connect() as c:
        row = c.execute(text('''SELECT r.rolsuper,r.rolbypassrls,r.rolcreaterole,r.rolcreatedb,
            pg_has_role(current_user,:g,'USAGE') AS member,
            pg_has_role(current_user,'cos_identity_owner','MEMBER') AS owner_member,
            pg_has_role(current_user,'cos_foundation_runtime','MEMBER') AS legacy_member
            FROM pg_roles r WHERE r.rolname=current_user'''), {'g': group}).mappings().one()
        other = 'cos_identity_auth' if group == 'cos_api_runtime' else 'cos_api_runtime'
        cross = c.execute(text('SELECT pg_has_role(current_user,:r,\'MEMBER\')'), {'r': other}).scalar_one()
        if not row['member'] or any(row[k] for k in ('rolsuper', 'rolbypassrls', 'rolcreaterole', 'rolcreatedb', 'owner_member', 'legacy_member')) or cross:
            raise RuntimeError('Dedicated minimally privileged service role required')
        # Validate EFFECTIVE login privileges too: direct grants must not bypass a
        # correctly configured group role. Parent must review combined feature lists.
        from .audit import RUNTIME_FUNCTIONS, AUTH_FUNCTIONS, RUNTIME_TABLES
        functions = set(c.execute(text('''SELECT p.proname||'('||replace(oidvectortypes(p.proargtypes),', ',',')||')'
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='cos_v6'
            AND has_function_privilege(current_user,p.oid,'EXECUTE')''')).scalars())
        expected = RUNTIME_FUNCTIONS if group == 'cos_api_runtime' else AUTH_FUNCTIONS
        tables = c.execute(text('''SELECT c.relname,
            has_any_column_privilege(current_user,c.oid,'SELECT') AS read,
            (has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
             OR has_any_column_privilege(current_user,c.oid,'INSERT,UPDATE,REFERENCES')) AS write
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='cos_v6' AND c.relkind IN ('r','p')''')).mappings().all()
        reads = {r['relname'] for r in tables if r['read']}
        expected_reads = RUNTIME_TABLES if group == 'cos_api_runtime' else set()
        if functions != expected or reads != expected_reads or any(r['write'] for r in tables):
            raise RuntimeError('Effective service privilege allowlist drift')
    # Do not emit parameter values through SQLAlchemy exceptions or SQL echo.
    if engine.echo or not engine.hide_parameters:
        raise RuntimeError('Identity engines require echo=False and hide_parameters=True')


def create_app(settings: Settings, runtime_engine: Engine, authentication_engine: Engine, *, oidc_transport=None, feature_routers=()) -> FastAPI:
    """Compose vetted feature routers; only runtime scope is exposed on requests.

    authentication_engine is closure-private and has only three login routines.
    Neither engine may be a migration administrator. No readiness override exists.
    """
    settings.validate()
    _engine_guard(runtime_engine, 'cos_api_runtime')
    _engine_guard(authentication_engine, 'cos_identity_auth')
    verifier = OIDCVerifier(settings.oidc, oidc_transport)
    cipher = Fernet(settings.state_encryption_key)
    app = FastAPI(title='Content OS M1 isolated identity API (development gates incomplete)',
                  version='0.1.0', openapi_url=PREFIX + '/openapi.json', docs_url=PREFIX + '/docs', redoc_url=None)
    install_errors(app)
    router = APIRouter(prefix=PREFIX, responses={s: {'model': ErrorEnvelope} for s in (401,403,404,409,422,428,429,500,503)})
    anonymous = {PREFIX + '/auth/login', PREFIX + '/auth/callback', PREFIX + '/onboarding/initiate',
                 PREFIX + '/openapi.json', PREFIX + '/docs', PREFIX + '/docs/oauth2-redirect'}

    def csrf(token):
        return hmac.new(settings.csrf_key, token.encode(), 'sha256').hexdigest()

    def origin(request):
        if request.headers.get('origin') != settings.origin:
            raise APIError('ORIGIN_INVALID', 403)

    @app.middleware('http')
    async def transaction_boundary(request, call_next):
        request.state.correlation_id = str(uuid4())
        try:
            if request.url.scheme != 'https' or request.headers.get('host', '').lower() != urlsplit(settings.origin).netloc.lower():
                raise APIError('ORIGIN_INVALID', 403)
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                origin(request)
            if request.url.path in anonymous:
                result = await call_next(request)
            else:
                token = request.cookies.get(COOKIE, '')
                if not 32 <= len(token) <= 256:
                    raise APIError('UNAUTHENTICATED', 401)
                def bind_request():
                    c = runtime_engine.connect().execution_options(isolation_level='READ COMMITTED')
                    try:
                        txn = c.begin()
                        c.execute(text("SET LOCAL lock_timeout = '5s'"))
                        c.execute(text("SET LOCAL statement_timeout = '10s'"))
                        user_id = call(c, 'api_bind', token=token,
                            csrf=request.headers.get('x-csrf-token', ''), writing=request.method not in ('GET', 'HEAD', 'OPTIONS'))
                        return c, txn, user_id
                    except BaseException:
                        c.close()
                        raise

                # Synchronous PostgreSQL I/O must not block the ASGI event loop.
                # Calls on the same connection are sequential, never concurrent.
                c, txn, user_id = await run_in_threadpool(bind_request)
                request.state.identity_connection, request.state.identity_user_id = c, user_id
                try:
                    result = await call_next(request)
                    await run_in_threadpool(txn.rollback if result.status_code >= 400 else txn.commit)
                finally:
                    request.state.identity_connection = None
                    await run_in_threadpool(c.close)
            result.headers['X-Correlation-ID'] = request.state.correlation_id
            result.headers['Cache-Control'] = 'no-store'
            result.headers['Referrer-Policy'] = 'no-referrer'
            result.headers['X-Content-Type-Options'] = 'nosniff'
            return result
        except APIError as exc:
            return error_response(request, exc.code, exc.status, exc.message)
        except DBAPIError as exc:
            code = getattr(getattr(exc.orig, 'diag', None), 'message_primary', '')
            return error_response(request, code if code in STATUS else 'DATABASE_UNAVAILABLE', STATUS.get(code, 503))

    def cookie(response, name, value, seconds):
        response.set_cookie(name, value, max_age=seconds, secure=True, httponly=True, samesite='lax', path='/')

    def session(request):
        result = call(connection(request), 'api_session')
        result['csrf_token'] = csrf(request.cookies[COOKIE])
        return result

    def expected(request):
        value = request.headers.get('if-match')
        if value is None:
            raise APIError('PRECONDITION_REQUIRED', 428)
        if not 3 <= len(value) <= 21 or not (value.startswith('"') and value.endswith('"')) or not value[1:-1].isascii() or not value[1:-1].isdigit() or not 1 <= int(value[1:-1]) <= 9223372036854775807:
            raise APIError('INVALID_ETAG', 422)
        return int(value[1:-1])

    def etag(response, value):
        response.headers['ETag'] = '"' + str(value) + '"'

    def page(request, kind, workspace, target, cursor, limit):
        scope = [str(request.state.identity_user_id), kind, str(workspace), str(target)]
        after_time, after_id = None, None
        if cursor:
            try:
                if len(cursor) > 3000:
                    raise ValueError()
                payload, mac = cursor.split('.')
                if not hmac.compare_digest(hmac.new(settings.cursor_key, payload.encode(), 'sha256').hexdigest(), mac):
                    raise ValueError()
                data = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
                if data['scope'] != scope:
                    raise ValueError()
                after_time, after_id = datetime.fromisoformat(data['time']), UUID(data['id'])
            except Exception:
                raise APIError('INVALID_CURSOR', 422) from None
        rows = call(connection(request), 'api_list', kind=kind, w=workspace, target=target,
                    after_time=after_time, after_id=after_id, n=limit+1)
        more = len(rows) > limit
        rows, next_cursor = rows[:limit], None
        if more:
            value = {'scope': scope, 'time': rows[-1]['sort_time'], 'id': rows[-1]['sort_id']}
            payload = base64.urlsafe_b64encode(json.dumps(value, separators=(',', ':')).encode()).decode().rstrip('=')
            next_cursor = payload + '.' + hmac.new(settings.cursor_key, payload.encode(), 'sha256').hexdigest()
        return {'items': [r['item'] for r in rows], 'has_more': more, 'next_cursor': next_cursor}

    @router.post('/auth/login', response_model=M.AuthRedirect, operation_id='startLogin')
    async def start_login(body: M.LoginStart, request: Request, response: Response):
        state, browser, nonce, pkce = (secrets.token_urlsafe(32) for _ in range(4))
        # No proxy headers trusted as an IP identity. Deployment proxy policy remains a gate.
        rate_key = digest(request.client.host if request.client else 'unknown')
        def start_transaction():
            with authentication_engine.begin() as c:
                return call(c, 'auth_start', sh=digest(state), bh=digest(browser), n=nonce,
                    v=cipher.encrypt(pkce.encode()).decode(), i=settings.oidc.issuer, r=body.return_path, rk=rate_key)
        transaction = await run_in_threadpool(start_transaction)
        cookie(response, LOGIN_COOKIE, browser, 600)
        return {'authorization_url': verifier.authorization_url(state, nonce, pkce), 'expires_at': transaction['expires_at']}

    @router.get('/auth/callback', response_model=M.Session, operation_id='completeLogin')
    async def complete_login(request: Request, response: Response, code: str = Query(min_length=1, max_length=4096), state: str = Query(min_length=32, max_length=256)):
        browser = request.cookies.get(LOGIN_COOKIE, '')
        if len(browser) < 32:
            raise APIError('INVALID_LOGIN', 401)
        # Consume and COMMIT before network/validation. A failure can never replay state.
        def consume_transaction():
            with authentication_engine.begin() as c:
                return call(c, 'auth_consume', sh=digest(state), bh=digest(browser))
        transaction = await run_in_threadpool(consume_transaction)
        try:
            pkce = cipher.decrypt(transaction['verifier_ciphertext'].encode(), ttl=600).decode()
        except Exception:
            raise APIError('INVALID_LOGIN', 401) from None
        identity = await verifier.complete(code, pkce, transaction['nonce'])
        token = secrets.token_urlsafe(32)
        def finalize_transaction():
            with authentication_engine.begin() as c:
                call(c, 'auth_finalize', tid=UUID(transaction['id']), i=identity['issuer'], s=identity['subject'],
                     e=identity['email'], n=identity['display_name'], th=digest(token), ch=digest(csrf(token)))
            with runtime_engine.begin() as c:
                call(c, 'api_bind', token=token, csrf='', writing=False)
                return call(c, 'api_session')
        result = await run_in_threadpool(finalize_transaction)
        result['csrf_token'] = csrf(token)
        cookie(response, COOKIE, token, 8*3600)
        response.delete_cookie(LOGIN_COOKIE, secure=True, httponly=True, samesite='lax', path='/')
        return result

    @router.get('/auth/session', response_model=M.Session, operation_id='getSession')
    def get_session(request: Request):
        return session(request)

    @router.get('/users/me', response_model=M.User, operation_id='getCurrentUser')
    def me(request: Request):
        return session(request)['user']

    @router.post('/auth/logout', response_model=M.Acknowledgement, operation_id='logout')
    def logout(request: Request, response: Response):
        call(connection(request), 'api_logout')
        response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='lax', path='/')
        return {'accepted': True, 'correlation_id': request.state.correlation_id}

    @router.post('/auth/workspace', response_model=M.Session, operation_id='switchWorkspace')
    def switch(body: M.WorkspaceSwitch, request: Request):
        call(connection(request), 'api_switch', w=body.workspace_id)
        return session(request)

    @router.post('/onboarding/initiate', response_model=M.OnboardingChallenge, operation_id='initiateOnboarding')
    def initiate(body: M.OnboardingStart):
        with runtime_engine.begin() as c:
            return call(c, 'api_onboarding', code=body.access_code, email=body.email)

    @router.post('/workspaces', response_model=M.Workspace, status_code=201, operation_id='createWorkspace')
    def create_workspace(body: M.WorkspaceCreate, request: Request, response: Response):
        result = call(connection(request), 'api_create_workspace', challenge=body.challenge_id, n=body.name, tz=body.timezone)
        etag(response, result['revision'])
        return result

    @router.get('/workspaces', response_model=M.Page[M.Workspace], operation_id='listWorkspaces')
    def workspaces(request: Request, cursor: str | None = None, limit: int = Query(25, ge=1, le=100)):
        return page(request, 'workspace', None, None, cursor, limit)

    @router.get('/workspaces/{workspace_id}', response_model=M.Workspace, operation_id='getWorkspace')
    def workspace(workspace_id: UUID, request: Request, response: Response):
        result = call(connection(request), 'api_read', kind='workspace', w=workspace_id, target=None)
        etag(response, result['revision'])
        return result

    @router.get('/workspaces/{workspace_id}/brands', response_model=M.Page[M.Brand], operation_id='listBrands')
    def brands(workspace_id: UUID, request: Request, cursor: str | None = None, limit: int = Query(25, ge=1, le=100)):
        return page(request, 'brand', workspace_id, None, cursor, limit)

    @router.get('/workspaces/{workspace_id}/brands/{brand_id}', response_model=M.Brand, operation_id='getBrand')
    def brand(workspace_id: UUID, brand_id: UUID, request: Request, response: Response):
        result = call(connection(request), 'api_read', kind='brand', w=workspace_id, target=brand_id)
        etag(response, result['revision'])
        return result

    def write_brand(w, b, body, request, response):
        key = request.headers.get('idempotency-key')
        if not key or len(key) > 200:
            raise APIError('IDEMPOTENCY_KEY_REQUIRED', 422)
        revision = expected(request) if b else None
        canonical = json.dumps({'body': body.model_dump(), 'brand': str(b), 'expected': revision}, sort_keys=True, separators=(',', ':'))
        result = call(connection(request), 'api_write_brand', w=w, b=b, n=body.name, tz=body.timezone,
                      expected=revision, key=key, h=digest(canonical))
        etag(response, result['revision'])
        return result

    @router.post('/workspaces/{workspace_id}/brands', response_model=M.Brand, status_code=201, operation_id='createBrand')
    def create_brand(workspace_id: UUID, body: M.BrandWrite, request: Request, response: Response):
        return write_brand(workspace_id, None, body, request, response)

    @router.patch('/workspaces/{workspace_id}/brands/{brand_id}', response_model=M.Brand, operation_id='editBrand')
    def edit_brand(workspace_id: UUID, brand_id: UUID, body: M.BrandWrite, request: Request, response: Response):
        return write_brand(workspace_id, brand_id, body, request, response)

    @router.get('/workspaces/{workspace_id}/memberships', response_model=M.Page[M.Membership], operation_id='listMemberships')
    def memberships(workspace_id: UUID, request: Request, cursor: str | None = None, limit: int = Query(25, ge=1, le=100)):
        return page(request, 'member', workspace_id, None, cursor, limit)

    @router.patch('/workspaces/{workspace_id}/memberships/{membership_id}', response_model=M.Membership, operation_id='editMembership')
    def edit_member(workspace_id: UUID, membership_id: UUID, body: M.MembershipEdit, request: Request, response: Response):
        result = call(connection(request), 'api_edit_member', w=workspace_id, target=membership_id,
                      roles=[r.value.lower() for r in body.roles], active=True, expected=expected(request))
        etag(response, result['revision'])
        return result

    @router.delete('/workspaces/{workspace_id}/memberships/{membership_id}', response_model=M.Membership, operation_id='revokeMembership')
    def revoke_member(workspace_id: UUID, membership_id: UUID, request: Request, response: Response):
        result = call(connection(request), 'api_edit_member', w=workspace_id, target=membership_id,
                      roles=None, active=False, expected=expected(request))
        etag(response, result['revision'])
        return result

    @router.get('/workspaces/{workspace_id}/memberships/{membership_id}/brand-grants', response_model=M.Page[M.BrandGrant], operation_id='listBrandGrants')
    def grants(workspace_id: UUID, membership_id: UUID, request: Request, cursor: str | None = None, limit: int = Query(25, ge=1, le=100)):
        return page(request, 'grant', workspace_id, membership_id, cursor, limit)

    @router.put('/workspaces/{workspace_id}/memberships/{membership_id}/brand-grants/{brand_id}', response_model=M.BrandGrant, operation_id='setBrandGrant')
    def grant(workspace_id: UUID, membership_id: UUID, brand_id: UUID, body: M.BrandGrantEdit, request: Request, response: Response):
        revision = expected(request)
        result = call(connection(request), 'api_grant', w=workspace_id, b=brand_id, target=membership_id, active=True,
                      connect=body.can_connect_social, expected=revision)
        etag(response, revision+1)  # Aggregate is the target membership, including new grants.
        return result

    @router.delete('/workspaces/{workspace_id}/memberships/{membership_id}/brand-grants/{brand_id}', response_model=M.Acknowledgement, operation_id='revokeBrandGrant')
    def revoke_grant(workspace_id: UUID, membership_id: UUID, brand_id: UUID, request: Request, response: Response):
        revision = expected(request)
        call(connection(request), 'api_grant', w=workspace_id, b=brand_id, target=membership_id, active=False, connect=False, expected=revision)
        etag(response, revision+1)
        return {'accepted': True, 'correlation_id': request.state.correlation_id}

    @router.post('/workspaces/{workspace_id}/invitations', response_model=M.LocalInvitationReceipt, status_code=201, operation_id='createInvitation')
    def invite(workspace_id: UUID, body: M.InviteCreate, request: Request, response: Response):
        token = secrets.token_urlsafe(32)
        result = call(connection(request), 'api_invite', w=workspace_id, i=settings.oidc.issuer, e=body.email,
                      r=[r.value.lower() for r in body.roles], brands=body.brand_ids, th=digest(token))
        etag(response, 1)
        return {'invitation': result, 'delivery': 'LOCAL_RECEIPT_NOT_SENT', 'token': token}

    @router.get('/workspaces/{workspace_id}/invitations', response_model=M.Page[M.Invitation], operation_id='listInvitations')
    def invitations(workspace_id: UUID, request: Request, cursor: str | None = None, limit: int = Query(25, ge=1, le=100)):
        return page(request, 'invitation', workspace_id, None, cursor, limit)

    @router.post('/invitations/accept', response_model=M.Membership, operation_id='acceptInvitation')
    def accept(body: M.InviteAccept, request: Request, response: Response):
        result = call(connection(request), 'api_accept_invite', token=body.token)
        etag(response, result['revision'])
        return result

    @router.delete('/workspaces/{workspace_id}/invitations/{invitation_id}', response_model=M.Invitation, operation_id='revokeInvitation')
    def revoke_invite(workspace_id: UUID, invitation_id: UUID, request: Request, response: Response):
        revision = expected(request)
        result = call(connection(request), 'api_revoke_invite', w=workspace_id, i=invitation_id, expected=revision)
        etag(response, revision+1)
        return result

    app.include_router(router)
    for feature_router in feature_routers:
        app.include_router(feature_router)

    def runtime_openapi():
        from fastapi.openapi.utils import get_openapi
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        schema.setdefault('components', {}).setdefault('securitySchemes', {})['SessionCookie'] = {
            'type': 'apiKey', 'in': 'cookie', 'name': COOKIE,
            'description': 'Opaque database session, Secure/HttpOnly; not a JWT or legacy workspace key.'}
        optimistic = {'editBrand', 'editMembership', 'revokeMembership', 'setBrandGrant', 'revokeBrandGrant', 'revokeInvitation'}
        for path, methods in schema['paths'].items():
            for method, operation in methods.items():
                operation['x-implementation-status'] = 'development-implemented'
                operation['security'] = [] if path in anonymous else [{'SessionCookie': []}]
                headers = []
                if method not in ('get', 'head', 'options'):
                    headers.append(('Origin', 'Exact configured HTTPS browser origin.'))
                    if path not in anonymous:
                        headers.append(('X-CSRF-Token', 'Session-bound CSRF token from session response.'))
                if operation.get('operationId') in optimistic:
                    headers.append(('If-Match', 'Strong quoted positive integer aggregate revision; no wildcard. Grants use membership revision.'))
                if operation.get('operationId') in ('createBrand', 'editBrand'):
                    headers.append(('Idempotency-Key', 'Actor/workspace/operation-scoped key, maximum 200 characters.'))
                operation.setdefault('parameters', []).extend({'name': name, 'in': 'header', 'required': True,
                    'description': description, 'schema': {'type': 'string', 'minLength': 1}} for name, description in headers)
        schema['info']['description'] = 'Isolated M1 runtime subset. Production refused. No external OIDC account or release acceptance proof. Local invitation receipts do not send mail.'
        app.openapi_schema = schema
        return schema

    app.openapi = runtime_openapi
    return app
