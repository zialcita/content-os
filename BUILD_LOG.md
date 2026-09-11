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
