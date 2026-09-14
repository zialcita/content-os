# M1 isolated identity API — reviewed development checkpoint

Integration update2026-09-14: direct review completed, fixes and18 added regressions documented in IDENTITY_REVIEW.md. Latest identity suite71 passed. Dependencies are pinned and global migration hooks now compose both audits, including reruns. Original scope notes below describe the initial isolated implementation; this update supersedes their pending-audit/dependency statements. Production/live-account/UI/upload gates remain open.

## Status and evidence boundary

Baseline inspected: **`e5bc4dde0aee434743704ccefb7f0c1fec5189ff`**, branch `engineering/v6-m0-foundation`. Read the complete 587-line v6 specification, API contracts, identity/authorization database design, complete foundation SQL, privilege audit and existing PostgreSQL test harness. The deferred `.github/` tree was not edited or staged. No existing foundation migration, schema, privileges, Alembic environment, old test, dependency file, legacy runtime or frontend was edited by this slice.

This is **real local PostgreSQL + real FastAPI ASGI execution**, not an in-memory session facade. The OIDC network is a **cryptographically signed fake IdP fixture**. Fixture accounts are not real OIDC account proof, pilot users, sent invitations, or release acceptance. No real provider, mail, onboarding account, invitee or external service was contacted. Production is unconditionally refused by this factory; there is no `V6_READY` or other readiness bypass.

Evidence lives at [`evidence/m1/identity/`](evidence/m1/identity/):

- `postgres-tests.log`, `pytest.xml`: actual assertions, PostgreSQL/ASGI runs; **71 passed, zero skipped** at the recorded run.
- `environment.json`: actual PostgreSQL/Python-package versions and fixture boundaries; no DSN.
- `runtime.openapi.json`: generated **implemented runtime subset**, not a copy/overwrite of `docs/contracts/target-v6.openapi.json` or legacy `/openapi.json`.
- `source-manifest.json`: SHA-256 of implementation/test inputs for the captured run.

Reproduce from the repository root:

```sh
python3 scripts/test_identity_postgres.py .venv/bin/python
```

The available outer `python3` is Python 3.9 with `pgserver`; the backend interpreter is `.venv` Python 3.12.14. The runner starts a **fresh PostgreSQL 16.2** temporary cluster, clears the parent environment before server startup, creates an allowlisted subprocess environment, and validates a disposable Unix-socket manifest. It never imports dotenv or reads/inherits `DATABASE_URL`. It runs only `backend/tests_identity` and migrates **`identity@head`**, so independent sibling migration branches do not change these tests.

Authlib **1.6.6**, cryptography **46.0.5**, cffi **2.1.1**, and pycparser **3.0** were installed into the existing `.venv`. These exact versions are now pinned in backend/requirements.lock and dependency compatibility was checked. The current FastAPI/TestClient stack emits two deprecation warnings (httpx/TestClient and AnyIO BlockingPortal); they are recorded, not hidden or counted as skipped tests.

## Factory and feature integration interface

```python
from secure_api.app import Settings, create_app
from secure_api.oidc import OIDCConfig

# No env or dotenv lookup, no implicit startup schema mutation.
settings = Settings(
    origin=exact_https_origin,
    oidc=OIDCConfig(
        issuer=pinned_issuer,
        client_id=public_pkce_client_id,
        authorization_endpoint=pinned_authorization_endpoint,
        token_endpoint=pinned_token_endpoint,
        jwks_uri=pinned_jwks_uri,
        redirect_uri=exact_https_origin + '/api/v6/auth/callback',
    ),
    state_encryption_key=fernet_key_bytes,
    csrf_key=independent_secret_bytes_32_or_more,
    cursor_key=independent_secret_bytes_32_or_more,
    mode='development',  # Explicit, mandatory. Any other mode raises.
)
app = create_app(settings, runtime_engine, authentication_engine,
                 feature_routers=[vetted_feature_router])
```

Both engines must use `echo=False, hide_parameters=True`. `runtime_engine` is a dedicated login inheriting **only `cos_api_runtime`**; `authentication_engine` is a different login inheriting **only `cos_identity_auth`**. The factory refuses superuser/BYPASSRLS/CREATEROLE/CREATEDB, membership in the definer-owner or legacy foundation role, and cross-membership between auth/runtime roles. Do not pass a migration administrator. No per-user database logins are needed; tests create exactly two service fixture logins and **zero `database_principals` mappings**.

Required public feature surface:

```python
from secure_api.dependencies import get_scope

scope = get_scope(request, workspace_id, brand_id, action='read')
# scope.user_id: UUID
# scope.workspace_id: UUID
# scope.brand_id: UUID | None
# scope.membership_id: UUID
# scope.connection: sqlalchemy.engine.Connection
```

`get_scope` is synchronous and returns a frozen `Scope`, not a generator. It works only inside a request handled by `create_app`. The middleware owns one **READ COMMITTED transaction** per authenticated request. It validates the opaque session and (for writes) CSRF before exposing the connection, then the dependency validates current workspace/brand/action authority. The transaction commits **before** successful response headers leave the middleware; error responses roll back. The connection is invalid outside the request. Feature code must not commit, roll back, retain, stream DB work after response start, or obtain an admin/authentication engine. Async feature endpoints should keep synchronous DB work bounded; long work must enqueue durable jobs rather than hold this transaction.

Actions: `read`, `edit`, `review`, `publish`, `connect`, `manage`, `owner`; `manage_read` is the database's read-only management helper. Ordinary brand content must pass a **real brand UUID**. A null brand is only for actual workspace-level identity/administration work, never permission to read every brand. `get_scope` rejects a write action invoked through GET/HEAD/OPTIONS. All non-owners, including admins, need an explicit active grant for brand content. Publisher `connect` additionally requires `can_connect_social`; combined roles are supported.

Feature tables/functions are not automatically granted or protected by this module. Their migrations must install their own narrow grants, RLS and security-definer authorization checks using `api_actor`/`api_allowed`/`api_authorize`, and the parent must review combined allowlists. Do **not** use foundation `actor()` or its per-user fixture bridge in new HTTP feature routes. The test-only `/api/v6/fixture/...` router exercises the interface and is never shipped by the factory or included in the saved runtime artifact.

## Database trust model and additive migration

`backend/alembic/versions/0002_sessions.py`:

- revision `0002_sessions`;
- `down_revision = '0001_m1_foundation'`;
- `branch_labels = ('identity',)`;
- loads `secure_api/session_schema.sql` and calls `audit_identity_privileges(connection)` within the migration transaction;
- retention-safe downgrade is refused; forward-fix instead of deleting identity/audit history.

New `cos_v6` tables: `sessions`, `login_transactions`, `identity_profiles`, `onboarding_authorizations`, `invitations`, `invitation_brands`, `identity_replays`. Additive columns: `identity_revision` on workspaces/memberships/brands and brand `timezone`. The old tables are not replaced and legacy sentinel data/default ACLs are preserved in tests.

Three NOLOGIN, non-superuser, non-BYPASSRLS roles:

| Role | Authority |
|---|---|
| `cos_api_runtime` | Exact public identity function allowlist and RLS SELECT on workspaces/memberships/brands/grants; **no table DML**, no private session/state rows, no auth finalization or foundation functions. |
| `cos_identity_auth` | Exactly `auth_start`, `auth_consume`, `auth_finalize`; no table reads or DML, no workspace/member/grant functions. It is the trusted verification boundary and may finalize verified `(issuer, subject)` into a user/session, not grant tenant access. |
| `cos_identity_owner` | NOLOGIN owner of only these definer functions; explicitly audited necessary table privileges and private helpers. Fixed `search_path=pg_catalog,cos_v6`. No role inheritance/schema CREATE. |

All new routines explicitly revoke PUBLIC EXECUTE, including private helper routines. None is granted to `cos_foundation_runtime`. `secure_api.audit.audit_identity_privileges(connection)` audits exact effective function signatures, private definer ownership/path, table/column DML/read drift, role attributes/inheritance, schema CREATE and RLS. Tests deliberately introduce PUBLIC functions, cross-role function grants, sensitive table and column grants, missing forced RLS and superuser drift and require rejection. The existing foundation global audit also continues to pass against this branch's migrated schema.

**RLS boundary is explicit, not overstated:** all seven new private tables ENABLE and FORCE RLS, with only the no-login definer role permitted by their policies; service roles have no direct access. Existing foundation tables keep their existing ENABLE-but-not-FORCE configuration and add role-specific identity policies. This preserves the original foundation ownership/fixture behavior. There is no claim of retrofit FORCE RLS across the entire old schema; the migration administrator remains privileged. This is a parent integration/security-review gate.

`cos.api_token` is not an actor UUID. It contains a **256-bit opaque unforgeable session capability** set with `set_config(..., true)` in the current transaction. `api_actor()` hashes it, resolves it against the private database session row, verifies expiry/revocation/user status, validates the identity binding, and locks the session `FOR SHARE`. Arbitrary `app.user_id`/`cos.actor_id` values or a session/user row UUID confer nothing. `cos.api_csrf` similarly must hash to the stored session CSRF hash on every mutation. The API role cannot read hashes or mint/finalize sessions. Authentication cannot be established by a caller-supplied user UUID.

Session SHARE locks serialize in-flight requests against session revocation. Workspace authorization locks use the same workspace-first permission-change lock as the foundation routines; fresh READ COMMITTED snapshots after lock acquisition prevent pre-revocation snapshot reuse. REPEATABLE READ/SERIALIZABLE are rejected rather than pretending they observe current permissions. A revoke that waits behind an already-authorized transaction takes effect for subsequent work; this is linearization, not retroactive cancellation. Pooled reuse resets local scope and each request explicitly binds its own token. Feature side effects outside this request must independently reauthorize.

## OIDC and cookie behavior

- Authlib `AsyncOAuth2Client`: authorization-code only, public-client PKCE **S256**, exact configured callback, state and nonce generated server-side. No implicit/hybrid flow or client-supplied provider endpoints.
- Login state is database-backed, ten-minute expiry, state/browser hashes plus nonce and **Fernet-encrypted PKCE verifier**. Browser cookie only contains an opaque random binding, not verifier, provider tokens, userinfo or signed-cookie identity state.
- `auth_consume` atomically consumes state and commits **before** token/JWKS networking. Wrong browser/state causes no provider call; failed token validation cannot replay consumed state. Successful finalization is separately single-use and wipes verifier ciphertext.
- Authlib `JsonWebToken(['RS256'])` and `CodeIDToken` perform JWT signature and standard ID-token validation. Issuer, audience, authorized party (including multi-audience `azp`), expiry, issue time, nonempty subject and nonce are explicitly required/checked. Current User contract requires a truly boolean `email_verified=true` and email; providers without verified email are rejected, not fabricated.
- JWKS comes only from the operator-pinned HTTPS URI; no redirects, environment proxies or token-header URL lookup. Response is bounded to 128 KiB/20 keys. Unknown/duplicate `kid`, RSA under 2048 bits, mismatched signing use/algorithm/key operations, private key material, `jku`, `x5u`, embedded `jwk` and unsupported critical extensions are rejected. Only RS256 is accepted; unsigned/HMAC/algorithm-confusion tokens are rejected.
- No userinfo request. Access/ID tokens exist only transiently during verification; neither tokens nor raw ID-token/userinfo payloads are persisted in database sessions/cookies. There is no refresh-token storage or refresh flow in this slice.
- Users are keyed by **unique `(issuer, subject)`**. Equal verified email strings never merge/link users. Successful subsequent login for the same identity reuses its user but issues a fresh opaque session token.
- Session cookie: `__Host-contentos-session`, Secure, HttpOnly, SameSite=Lax, Path=/, no Domain, eight-hour absolute expiry. DB stores only SHA-256 token/CSRF hashes. CSRF response token is derived by server-key HMAC, not a provider credential; SameSite is **not** CSRF protection.
- Browser mutations require exact Origin **and** `X-CSRF-Token`. Login/onboarding initiation require exact Origin; OIDC callback instead has its one-use browser-bound state/nonce/PKCE defenses. No wildcard CORS or legacy-key alternative.
- Logout revokes the DB row and clears the cookie. Reusing the old cookie is rejected. Responses are no-store; correlation/error responses omit SQL/provider secret values. SQLAlchemy echo is forbidden and parameter values are hidden.
- Login initiation uses a DB-backed per-source-IP limit of ten per minute. Forwarded IP headers are not trusted. More comprehensive abuse/proxy policy remains a gate; opaque onboarding/invitation secrets are at least 256 bits in the implementation/test issuance path.

## Implemented exact runtime paths

All below are under **`/api/v6`** (the planned contract's server prefix). Unimplemented operations are absent, not fake-success stubs.

| Method | Path | Behavior |
|---|---|---|
| POST | `/auth/login` | Persist login transaction; authorization URL + opaque browser cookie. |
| GET | `/auth/callback` | One-use code/state flow; verified ID token → opaque DB session. |
| GET | `/auth/session` | Current database-backed session + CSRF token. |
| POST | `/auth/logout` | Revoke current session. |
| POST | `/auth/workspace` | Switch UI active workspace only after membership check; not a permission grant. |
| GET | `/users/me` | Verified current identity. |
| POST | `/onboarding/initiate` | Redeem one-use preauthorized code into challenge. |
| POST | `/workspaces` | Consume challenge bound to exact issuer/subject and create owner membership atomically. |
| GET | `/workspaces` | Paginated currently accessible workspaces. |
| GET | `/workspaces/{workspace_id}` | Authorized workspace read/ETag. |
| GET, POST | `/workspaces/{workspace_id}/brands` | Grant-filtered list; authorized create with idempotency. |
| GET, PATCH | `/workspaces/{workspace_id}/brands/{brand_id}` | Scoped read; edit with If-Match + idempotency. |
| GET | `/workspaces/{workspace_id}/memberships` | Management-authorized list; revisions in items. |
| PATCH, DELETE | `/workspaces/{workspace_id}/memberships/{membership_id}` | Manage roles/revoke; If-Match; owner protected. |
| GET | `/workspaces/{workspace_id}/memberships/{membership_id}/brand-grants` | Management-authorized list. |
| PUT, DELETE | `/workspaces/{workspace_id}/memberships/{membership_id}/brand-grants/{brand_id}` | Explicit grants/revoke; target **membership aggregate** If-Match, including first grant. |
| POST, GET | `/workspaces/{workspace_id}/invitations` | Local receipt issuance (no mail) and authorized list. |
| POST | `/invitations/accept` | Verified intended identity + valid single-use secret. |
| DELETE | `/workspaces/{workspace_id}/invitations/{invitation_id}` | Authorized revoke with invitation ETag. |
| GET | `/openapi.json`, `/docs` | Distinct generated runtime OpenAPI/docs. |

### Concurrency, pagination and exact deviations

Collections default to 25/max 100 and use stable `(created_at,id)` ordering. HMAC-authenticated opaque cursors bind actor, collection, workspace and membership filters. Grant filtering is applied before the page limit; omitting brand does not broaden visibility.

Strong quoted positive integer ETags: missing 428, stale 409, wildcard/weak/invalid 422. Brand mutations persist actor/workspace/operation/key/hash/original response transactionally; repeat matching request replays **before** stale revision checks, differing input conflicts with no mutation. Ordinary replay rows are retained conservatively; a seven-day cleanup/retention job remains unimplemented. Metadata mutations write audit rows; invitation tokens and provider state are never audit metadata.

Known, explicit target-contract deltas:

1. `createInvitation` returns typed **`LocalInvitationReceipt {invitation, delivery: LOCAL_RECEIPT_NOT_SENT, token}`**, rather than pretending a target `Invitation` was emailed. The secret is returned only at local issuance, hashed at rest, never shown by list. Default expiry is seven days. Acceptance checks current session identity's pinned issuer and cryptographically verified email, records `accepted_identity_id`, checks expiry/state and creator's still-current management authority, then creates normalized membership/grants atomically. It never overwrites existing memberships or owners. This is not external mail-delivery proof.
2. `MembershipEdit.state` supports only ACTIVE; DELETE persists REVOKED. Target SUSPENDED is rejected (422) because the preserved foundation membership constraint does not support it. No fake suspension or silent rewrite is claimed.
3. Brand profile APIs are absent; `current_profile_version_id` is legitimately null for new brands, not an invented profile/version. Voice generation is absent, not simulated success.
4. **Ownership transfer is not implemented or advertised.** There is no function that changes the owner pointer after onboarding and no admin self-promotion path. Implement recent verified owner reauthentication plus explicit target acceptance/one-use transfer authorization before exposing the planned transfer route. Current absence is a remaining M1 gate, not acceptance evidence.
5. Scoped API credentials, external OIDC project selection/client secrets, reauthentication, key rotation UI, session-management/revoke-all, provider-logout integration, invitation delivery and frontend are not implemented. Public signup is not enabled.

Pilot workspace creation is possible **only** after a privileged operator has explicitly provisioned an `onboarding_authorizations` row with code hash, exact intended issuer/subject/email and expiry. Neither API role can insert these authorizations. The tests provision only fictional fixture rows in a disposable cluster. There is no live onboarding script, invented pilot owner or authorization based on a workspace label/email alone.

## Assertions and remaining integration gates

The 53-test suite includes real HTTP→PostgreSQL onboarding, invitations/acceptance, workspace switching, multi-workspace and brand-denied reads; editor/reviewer/publisher/admin role matrix; combined roles and publisher connection capability; owner protection; expired invitation/session/login; cryptographic issuer/aud/azp/nonce/subject/expiry failures; bad signatures and malicious JWKS headers/keys/algorithms; state/browser replay; CSRF/Origin; no email linking; no sensitive direct DML or auth-role impersonation; pooled transaction reset and UUID GUC spoofing; READ COMMITTED enforcement; session-revocation blocking race and permission revoke after an earlier transaction snapshot; idempotency/If-Match; signed cursor/filter isolation; migration preservation and privilege-audit negative tests.

Parent integration must still:

- Independently audit/merge identity with upload/job modules and extend exact runtime allowlists only for vetted functions/table policies. No feature should receive a privileged/admin connection.
- Completed in this checkpoint: global Alembic migration and rerun hooks now compose identity and foundation audits.
- Completed in this checkpoint: foundation regressions explicitly target001, while separate identity tests validate full head and combined-schema accounting; fixed table-count and privilege assertions are preserved.
- Pin/review installed dependencies in the authorized lockfiles; review migration role provisioning, service-role effective privileges and RLS across the combined schema. Validate operation revision behavior if any non-fixture writer can also mutate membership/grant rows through old foundation routines.
- Implement owner transfer with target acceptance and recent verified reauthentication, SUSPENDED membership lifecycle, global token/session cleanup, key rotation/recovery and explicit privacy/retention policies.
- Complete trusted HTTPS proxy/Host policy, access-log query/header redaction, request/time/connection limits, rate limits beyond login, distributed-load behavior, cookie deployment tests, secrets management and PostgreSQL backups/restore. The development factory does not certify deployment log configuration or availability under attack.
- Select and authorize an actual OIDC provider/project and run a real account integration gate; this fixture is not provider or identity ownership proof. Current client is public-client PKCE; confidential-client authentication/discovery is not claimed.
- Wire UI, private uploads, durable workers/budgets, schemas and corresponding acceptance gates together. This isolated slice is **not M1 complete, R1-ready, deployed, or real-provider accepted**.
