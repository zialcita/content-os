# Build log

## 2026-09-11 — M0 inventory, contracts and preservation

Source commit: d3e3f9934681dcb29e65194f9699566165ccd813, main. Work branch: engineering/v6-m0-foundation. User approved the v6 plan before branch work. This log records engineering deliverables, not a completed R1 product.

### Delivered

- Adopted the exact uploaded v6 master specification under docs/spec; preserved original README/MVP contract bytes under docs/history and made root scope precedence explicit.
- CURRENT_STATE inventory: 14 existing ORM tables, 26 runtime-declared API paths, dependency/configuration modes, deployment unknowns and critical security/durability gaps. Source snapshots include PostgreSQL DDL compiled from existing metadata and actual declared legacy OpenAPI.
- Database catalog/ERD, immutable typed version and approval rules, tenant-consistent constraints, role/RLS boundaries, additive cos_v6 migration/backfill/quarantine/rollback plan. No migration applied.
- Target OpenAPI3.1, JSON Schema events, lifecycle and coverage: 128 paths, 154 operations, 241 schemas, 23 typed events; all marked planned, no runtime route replaced by aspirational docs.
- ADR0001 stack/providers and ADR0002 data/workers; dated production/social capability research, owner decision register and deployment/recovery readiness.
- 32-ticket dependency-ordered backlog; all AT01–30 mapped to explicit fixture/action/persisted assertion/evidence. All v6 ATs remain NOT RUN.
- Exact tested backend version lock; safe local baseline/snapshot runners, disposable real PostgreSQL probe and synthetic dotenv isolation regression tests.

### Verification and evidence

| Command/check | Result | Evidence |
|---|---|---|
| Python3.12 scripts/verify_m0.py | 3 legacy tests passed, 1 deprecation warning; isolated SQLite/explicit simulation | docs/evidence/m0/safe-baseline-pytest.log and summary JSON |
| pgserver scripts/probe_m0_postgres.py .venv/bin/python | PostgreSQL16.2 initialized with vector available; 3 legacy tests passed, 1 warning | postgres-baseline.log, postgres-pytest.log; runner passes generated local DSN before fixture import |
| scripts/snapshot_m0.py | 14 tables/26 declared paths snapshotted without lifespan/provider execution | legacy.schema.json, legacy.schema.sql, legacy.openapi.json |
| unittest discover docs/contracts | 42 passed, zero skipped including JSON Schema/OpenAPI validators | contracts-unittest.log |
| build_contracts.py --check | All four generated artifacts reproduce exactly | generator check at final validation |
| scripts/test_m0_safety.py | 5 synthetic isolation tests passed | safety-tests.log; no real secrets inspected |
| npm ci --prefix frontend --ignore-scripts | BLOCKED HTTP403 at locked undici-types tarball on registry.npmjs.org | npm-ci.log; network-access request pending |
| npm run build --prefix frontend | NOT VERIFIED, next absent after install failure | frontend-build.log |
| git diff --check | Passed at review checkpoint; rerun before commit | no whitespace errors |

### Review repairs before implementation

Independent review identified SCRIPT identity, missing voice/clip/rendition approval mappings, paid pre-plan deadlock, timeline output ownership cycles, null-brand administrative job scope, wrong generic job-action role gate and mixed credit/money ledger contracts. The designs/contracts were reconciled and regression checks added. Final review corrected manual assets' nullable plan and exact final-cut rendition binding through clip requests/selections. Test runners now disable dotenv before application imports, not merely clear process environment. Detailed historical reviewer notes in safety evidence are observations at review time, not unresolved current blockers; final bindings tests cover the last two schema repairs.

### Requirement coverage and limits

This change addresses v6 §§1,3,4,7–9,13–16,19–23 at M0 design/inventory level. It does not implement the future database/API/security/worker features described. The source backend/frontend business logic is unchanged. Local simulated fixtures never settle real spend or establish media/publication acceptance. No calls to real AI/transcription/avatar/assembly/social services, no production databases, invitations, external posts, merge or deployment. Live paid budget remains unauthorized/zero by policy; legacy runtime defaults are documented unsafe and not altered in M0.

### Gate disposition / next work

M0 artifacts are delivered for review, but full M0 acceptance remains pending successful frontend dependency installation/build. Shotstack account-level capability proof is separately recorded externally blocked pending approved credentials, privacy settings and budget. The baseline is reproducible for backend/contracts; frontend is not yet verified.

Next: after registry permission, reproduce install/build without changing source lock to conceal the access failure; record compiler issues and repair if found. Proceed to M1 additive migrations, identity/tenant checks, durable jobs/reservations and private upload shell using the reviewed contracts. No M1 gate is claimed passed. Critical early owner questions: OIDC/hosting reuse, exact LinkedIn account type and TikTok eligibility; see docs/DECISIONS_REQUIRED.md. M2+ also need approved provider budgets, identities/consent and representative brand fixtures. External gates do not reduce release requirements.


## 2026-09-11 05:38 UTC — Confirmed decisions and registry retry

Owner confirmed LinkedIn personal profiles AND company pages, no existing identity service, and reported npm network approval. Hosting was skipped; no project is selected or provisioned. Updated decision register accordingly.

Retried npm ci against the unchanged package-lock and registry; exit1/HTTP403 persists. A direct diagnostic request to the exact tarball returned a network-policy denial, not a package/compiler failure. Evidence: docs/evidence/m0/npm-ci-retry-20260911.log, npm-registry-response-headers.txt and npm-registry-response-body.txt. A fresh domain access request was surfaced; no bypass, alternate registry or lockfile rewrite attempted. M0 frontend gate remains blocked; no M1/runtime implementation is claimed. Prior passing backend/contracts evidence is unchanged.


## 2026-09-11 — Network gate resolved and M1 component implementation

Platform explicitly granted registry access. The original frontend lock installed; Next15.5.25 compiled/type-checked/generated8 static pages. Original npm audit showed2 package findings through PostCSS. Applied targeted PostCSS8.5.28 override and pinned direct dependencies to tested lock versions (no Next major upgrade); clean install, npm audit zero reported vulnerabilities, build passed again with visible simulation banner. M0 local gate is now satisfied; external assembly/account proof remains explicitly blocked. Original failure/build/audit records retained.

Implemented additive Alembic foundation (19 cos_v6 tables plus migration history), runtime reads/controlled writes under local session-user fixture identities, integer simulated workspace/job caps, durable fenced job/event primitives. Production/live paths deliberately absent. Independent review confirmed and repaired stale-isolation authorization, NULL outbox lease and future-function privilege-audit defects. Full foundation suite44 pass on actual disposable PostgreSQL16.2. Legacy safety suite59 pass: production/import fail closed, explicit simulation/empty credentials, zero hard cap, global scheduler/tick disabled, simulation labels. Contracts42 pass, synthetic isolation5 pass, Python dependency check pass. Final named logs under docs/evidence/m1. These are component proofs, not full M1/AT release acceptance.

Updated env example to explicit demo mode and zero cap, locked backend/Alembic dependencies and Docker copy, added local-gates CI workflow (hosted execution not yet certified at this log entry). Historical PostgreSQL probe refuses altered fixtures, and helper output paths now preserve M0 evidence. Foundation and legacy suites run separately with cleared environment/disposable data. No production DSN, OIDC account, live provider, real user onboarding, paid call, post, merge or deployment.

Changed-file groups: backend/foundation, backend/alembic, backend/tests_foundation, runtime config/main/policy/spend/health/tests, safe scripts, frontend dependency locks/simulation banner, environment/Docker/CI, progress/decision/acceptance docs and evidence. See M1_PROGRESS.md for exact scope and remaining M1 gate: identity/session/API bridge, full immutable registry/approval/multicap and job lifecycle, private uploads, production roles and integrated acceptance.


## 2026-09-11 — Authorized CI deferral

Owner instruction: Commit code; defer CI file. Rechecked PR2 remains open/draft on engineering/v6-m0-foundation at0534244dc751c2b802f516875519aa7ed2d0f505 and main is unchanged. Preserve .github/workflows/ci.yml locally; explicitly exclude workflow files from this delivery. CI installation/hosted evidence remains a pending M1 acceptance gate. The prepared backend/frontend/scripts bytes match the previously tested payload; only delivery/status documentation and metadata are updated for this retry. No tests are relabeled as hosted CI. No alternate credentials, repository, branch, merge or deployment.
