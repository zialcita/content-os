# Identity checkpoint — direct engineering review

Date: 2026-09-14 UTC. Baseline: e5bc4dde0aee434743704ccefb7f0c1fec5189ff. Scope: the locally preserved identity slice, its additive migration, service-role authorization, ASGI API boundary and isolated regression harness. This is a direct engineering review and test record, not an independent security certification or production acceptance.

## Reviewed boundaries

Read OIDC configuration/verifier, app factory/middleware/routes, request-scope dependency, identity SQL and exact privilege audit, models/errors, both migration revisions and existing foundation/identity fixtures. The design uses server-side opaque sessions, state/browser-bound authorization code + S256 PKCE, Authlib signature and ID-token validation, separate auth/runtime roles, hashed session/CSRF secrets, transactional current-authority checks and explicit role/brand grants. No provider tokens are stored in browser cookies. Equal email does not merge users; invitations require a verified session identity from the selected issuer. Owner creation requires a separately provisioned onboarding authorization.

## Findings repaired before this checkpoint

| Finding | Repair | New evidence |
|---|---|---|
| Synchronous PostgreSQL checkout/bind/commit and login-state I/O ran on the async request loop | Move these sequential operations to the thread pool; authenticated request SQL has 5s lock and 10s statement timeouts | Instrumented database event test proves login/session/logout SQL runs off the ASGI loop |
| Concurrent session-changing requests could contend on SHARE-to-UPDATE lock upgrades | Acquire the session mutation lock in api_bind before SHARE authorization checks | Two simultaneous workspace-switch requests sharing a session both finish successfully |
| Authlib token HTTP response was buffered without a download-size bound | Bounded transport caps token/JWKS wire responses at128KiB; request identity encoding and reject compressed responses; enforce20s whole exchange deadline | Streaming oversized token stops after crossing the cap; compressed response and slow-stream deadline rejected |
| Numeric ID-token claims could admit malformed non-finite values | Require finite numeric expiry/issue time and expiry later than issue time | Signed fixture tokens with NaN/infinities/invalid ordering never create sessions |
| Exact API Host/scheme boundary was not checked | Require the configured HTTPS origin host on all endpoints, in addition to Origin+CSRF for browser writes | Host mismatch/alternate-port requests denied before login state creation |
| Invitation list omitted the version needed to revoke safely | Include positive revision in SQL response, runtime model and planned contract; keep exact If-Match | List→revoke uses revision1, returns revision2 and updated ETag; contract regression prevents omission |
| Session user/identity relationship was checked at authorization but not a composite database FK | Add unique identity(user_id,id) and matching sessions FK within uncommitted additive revision002 | Deliberate mismatched session identity rejected with PostgreSQL foreign-key violation |
| SQL list bound permitted NULL via three-valued logic | Explicitly reject NULL page size | Direct scoped SQL call rejects without an unbounded response |
| New identity privilege audit was missing from global migration reruns | Compose foundation and installed-identity audits after every migration and on reruns | Full-head rerun and deliberate identity grant drift tested; original foundation audit remains intact |
| Foundation tests assumed one head and a19-table schema | Pin original suite to revision001; explicitly target the synthetic unsafe revision in that regression; add separate combined-schema test | Original44 tests pass; identity suite also exercises original simulation ledger after002 and full-head upgrade preservation |

No edits were made to the already committed revision001 schema. Revision002 had not been committed/applied outside disposable rehearsals; its reviewed SQL is now the checkpoint's new migration. Further changes after delivery must use a new revision.

## Integration completed

- Pinned Authlib1.6.6, cryptography46.0.5, cffi2.1.1, pycparser3.0 in the tested backend lock.
- Added foundation.migration_audit as the shared migration acceptance hook; it preserves explicit connections and never reads a database URL from ambient configuration.
- Identity runtime remains a separate development-only factory. Legacy main stays fail-closed; no readiness environment variable enables production.
- Runtime OpenAPI represents only implemented routes. Target contracts remain separate; the invitation revision addition regenerates deterministically.
- New evidence is stored under docs/evidence/m1/identity. The original interrupted-run evidence and partial upload SQL remain separate local recovery material, not authoritative new-run evidence.

## Local proof and exclusions

Identity suite contains71 passing cases (the original53 plus18 review/integration regressions), using actual PostgreSQL16.2 and FastAPI/ASGI with cryptographically signed fake IdP responses. Final full regression results and commands are in BUILD_LOG.md and docs/evidence/m1/identity-checkpoint. These are fixture identities, not real OIDC account ownership or mail delivery. No real provider network call, user invitation, spending, publishing, merge or deployment occurred.

Remaining M1 gates: real approved OIDC project and deployment topology, frontend login wiring, ownership-transfer acceptance/reauthentication, unsupported suspended-member lifecycle, operational key rotation/recovery/rate limits/proxy-log privacy, private uploads and scanner workers, full registry/approval and job/accounting integration, production role hardening and integrated acceptance. CI installation/hosted tests remain deferred by the owner. Partial backend/content_core SQL is excluded from this identity commit.
