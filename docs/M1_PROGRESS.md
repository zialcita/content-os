# M1 progress — local foundation implemented, milestone still open

Identity update2026-09-14: backend login/session/CSRF/workspace/brand/invitation routes now have a reviewed development implementation, with additive migration002, composed privilege audits and71 PostgreSQL/ASGI tests using a signed fixture IdP. See IDENTITY_REVIEW.md and M1_IDENTITY_API.md. The earlier foundation-only descriptions below remain checkpoint history. Identity UI, real-provider acceptance and remaining M1 features are not complete.

Date: 2026-09-11 UTC. Continuation baseline commit: 0534244dc751c2b802f516875519aa7ed2d0f505. Changes and evidence are identified by file hashes in each suite; the enclosing Git commit supplies the delivery revision. No production provisioning, migration, paid API work or social publication occurred.

## M0 local gate closed

The platform delivered a confirmed registry permission event. The unchanged frontend package-lock then installed successfully and Next.js15.5.25 compiled, type-checked and generated all eight static pages. Evidence: evidence/m0/npm-ci-granted.log and frontend-build-granted.log. This establishes the previously missing reproducible frontend baseline; old 403 logs remain historical evidence.

The original npm audit identified two vulnerable package entries arising from PostCSS advisories. Instead of an automatic forced Next.js major upgrade, pinned the existing installed direct versions and applied the targeted Next→PostCSS8.5.28 override. Reinstalled from the resulting lock, audited and rebuilt: **zero vulnerabilities reported by npm audit**, build successful. This is the registry's reported dependency audit, not a comprehensive security certification. Original and patched audits are retained. The main Next.js version is unchanged.

M0 inventory/contracts/local-baseline gate is satisfied. Shotstack account-level capability proof and other provider account approvals remain explicitly externally blocked; no documentation lookup is treated as live proof.

## Implemented M1 subsets

### PostgreSQL foundation

Alembic revision0001 creates 19 cos_v6 tables plus a separate migration-history table, without changing legacy public tables. It implements fixture identities/memberships/brands, tenant-safe reference constraints, scoped runtime reads, controlled mutation functions, jobs/steps/fences, simulated workspace/job reservations and immutable settlement/allocations, outbox/inbox and attempt-aware restart recovery. Downgrade refuses to delete history. Details: [M1_FOUNDATION.md](M1_FOUNDATION.md).

The fixture principal bridge binds a database session user to a synthetic verified identity. It is not OIDC or the production connection-pool architecture. Only LOCAL_SIMULATION jobs/accounting are enabled; no live money or provider dispatch can use this subset. Full registry/assets, campaign/plan/preproduction authority, real session flow and worker API integration remain unimplemented. RLS is enabled for runtime reads but FORCE-RLS/production definer ownership separation is not claimed ready.

### Legacy runtime safety

Unconfigured/production startup refuses before constructing the legacy database engine. Only explicitly selected development/test simulation can run, and real credentials or real engine selections are rejected. The API no longer starts a global scheduler, and the unsafe workspace-key global tick always refuses. Zero cannot fall back to a nonzero spending allowance. Fixture counters and publication-looking states are labeled simulation in the API and frontend. Old float accounting is still unsuitable for production and is not connected to real spending. Details: [M1_RUNTIME_SAFETY.md](M1_RUNTIME_SAFETY.md).

### Reproducibility and CI

Backend requirements now consume the exact tested lock, including Alembic1.18.4/Mako1.4.1/MarkupSafe3.0.3; Dockerfile copies the lock before installation. Frontend direct dependencies match tested locked versions. Prepared .github/workflows/ci.yml locally for contracts, synthetic configuration isolation, legacy runtime safety, disposable PostgreSQL migrations/concurrency, npm audit and frontend build. On2026-09-11 the owner explicitly authorized committing the tested code while deferring this CI file after GitHub rejected the initial write. The workflow is NOT included in this commit and remains preserved in the local working tree and the previously delivered snapshot. Installing/running hosted CI remains a pending M1 gate, not a removed requirement. No deployment step or repository secret is used.

Historical M0 PostgreSQL runner now refuses a changed legacy fixture rather than incorrectly presenting its forced SQLite run as PostgreSQL evidence. Current PostgreSQL evidence comes only from test_foundation_postgres.py. Snapshot/regression helpers write under evidence/m1/regression, preserving M0 records.

## Independent review and fixes

Three confirmed defects were repaired before delivery:

1. Stale REPEATABLE READ authorization could outlive committed grant revocation. Central SQL actor/authorize now enforce READ COMMITTED for this bounded slice; unsupported isolation is rejected even through direct SQL. Two-connection regression covers snapshot-before-revoke.
2. NULL lease duration could strand outbox delivery. Explicit NULL/worker/token checks and owner/expiry/state constraints now reject inconsistent leases without mutation.
3. Schema-level default-privilege revocation did not remove PostgreSQL's global PUBLIC function-execution default. Removed the false default-security promise; current functions are explicitly revoked and an exact-signature audit checks every revision and head rerun. Tests prove an unsafe new definer or grant is rejected and its migration rolled back. No global administrator defaults were changed.

## Final local evidence

| Suite | Result | Evidence |
|---|---|---|
| PostgreSQL foundation | 44 passed, no failures/skips; real disposable PG16.2 | evidence/m1/foundation/postgres-tests.log, pytest.xml, environment.json, source-manifest.json |
| Legacy runtime safety and baseline | 59 passed, no failures/skips; one TestClient deprecation warning | evidence/m1/runtime-safety/pytest.log and pytest.xml |
| API/event target contracts | 42 passed, no skips; deterministic output | evidence/m1/integration/contracts.log |
| Synthetic environment/dotenv isolation | 5 passed | evidence/m1/integration/isolation.log |
| Frontend build/type checks after patches/banner | Passed | evidence/m1/integration/frontend-build.log |
| npm dependency audit | Zero reported vulnerabilities | evidence/m1/integration/npm-audit.json |
| Installed Python dependency compatibility | uv pip check passed | recorded integration command; not a Python CVE audit |

These are local component proofs, not full AT or milestone acceptance. Foundation scenarios provide partial local coverage for AT01/02/05/06/07/08/28/29; runtime safety provides partial AT27/29 coverage. Full integrated AT verdicts remain open, including HTTP/object access, exact approved-version lineage and provider/human gates.

## Remaining M1 gate and next dependency order

1. Expand immutable registry/approval core and preserve/quarantine representative legacy data with verified mappings; production privileges/ownership and pool-safe actor boundary.
2. Backend Authlib OIDC/session/CSRF/invitation/brand routes are implemented for development and locally verified. Remaining: frontend login wiring, ownership transfer/reauthentication, full lifecycle/operational hardening and real approved OIDC account proof. Hosting/issuer still require owner selection before provisioning.
3. Connect the real API/jobs/outbox workers; full lifecycle/cancellation/multi-step/reconciliation and live-safe multi-cap authority. Do not expose LOCAL_SIMULATION fixture functions as production operations.
4. Private upload shell and quarantine/scanning lifecycle, then complete migration/isolation/concurrency/restart and OIDC/storage integration gates.

No M2 advancement or full M1 completion is claimed. Both LinkedIn personal and company publishing are confirmed future pilot requirements. Production hosting, users/reviewer, provider credentials/consent, positive budgets and controlled-publication authorization remain owner gates—not reasons to fabricate outcomes or reduce scope.
