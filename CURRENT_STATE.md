# Current state — M0

Date: 2026-09-11 UTC. This is source inspection and disposable-local evidence, not a production audit.

## Provenance

- Repository: https://github.com/zialcita/content-os
- Inspected source commit: `d3e3f9934681dcb29e65194f9699566165ccd813` (commit, not tree).
- Original branch: `main`; remote HEAD points to main. API listing reports main unprotected. Rechecked before work.
- Commit subject: Merge pull request #1 from zialcita/cursor/content-os-mvp-skeleton-8f5d.
- Work branch: `engineering/v6-m0-foundation`; clean checkout before additive M0 changes.
- No AGENTS.md, CONTRIBUTING policy, CI configuration or deployment manifest beyond Dockerfile/compose in tracked baseline files. No production project/account/URL supplied or inspected. Do not infer a live deployment from the historical README's Render-ready claim.
- Adopted source: uploaded v6 at docs/spec/CONTENT_OS_ASTRA_BUILD_SPEC_v6.md, preserved byte-for-byte. Historical README/MVP preserved verbatim under docs/history.
- Exact current M0 change commit is identified by the Git commit containing this file and the draft PR; do not use this baseline SHA as the subsequent artifact commit.

## Measured results

| Check | Result | Evidence and limitation |
|---|---|---|
| Original legacy tests, isolated SQLite | 3 passed; one TestClient deprecation warning | docs/evidence/m0/safe-baseline-pytest.log; all provider behavior simulated |
| Disposable real PostgreSQL initialization | Passed on PostgreSQL 16.2; vector/plpgsql available | postgres-baseline.log; pgserver-packaged local binary over local socket, no remote DB |
| Legacy tests on that PostgreSQL | 3 passed; one warning | postgres-pytest.log plus scripts/probe_m0_postgres.py; same generated disposable DSN passed explicitly, legacy setdefault cannot replace it |
| v6 offline contract suite | 42 passed, zero skipped | contracts-unittest.log; includes Draft2020-12 and OpenAPI3.1 validation; not endpoint execution |
| Generated contracts deterministic | Passed | build_contracts.py --check; 128 paths, 154 operations, 241 schemas, 23 event types |
| Current runtime/schema snapshot | 14 ORM tables; 26 declared paths | legacy.schema.json, legacy.schema.sql, legacy.openapi.json; lifespan not started during snapshot |
| npm ci from existing lockfile | BLOCKED: HTTP403 downloading undici-types-6.21.0.tgz from registry.npmjs.org | npm-ci.log; network-access approval requested, no alternate registry substituted |
| Next.js production build | NOT VERIFIED; command failed because next was not installed | frontend-build.log; consequence of dependency failure, not evidence of a source compile error |
| Real provider/account, public/private publication, restore, UAT | NOT RUN | Zero owner-authorized live budget; no account or fixture authorizations supplied |

M0 is not fully accepted while the reproducible frontend build is unresolved. Its inventory/design/contract deliverables are reviewable. M1–M6 feature gates and AT-01–AT-30 remain NOT RUN; no legacy fixture result is a substitute. M0 provider discovery is documentation evidence; Shotstack real capability proof is externally blocked pending approved account/budget/privacy settings.

## Runtime and dependencies

Host initially offered Python 3.9.25, Node 24.14.1 and npm 11.11.0; Docker and system PostgreSQL were absent. Installed a local Python 3.12.14 to match backend/Dockerfile's 3.12 family. An isolated venv resolved the baseline lower bounds to FastAPI 0.141.1, SQLAlchemy 2.0.52, Pydantic 2.13.5, Starlette 1.6.0, HTTPX 0.28.1, psycopg 3.3.5 and uvicorn 0.52.4. Full exact resolver result is backend/requirements.lock (same bytes as evidence baseline-python-freeze.txt). This is an exact tested baseline lock, not a vulnerability audit or blanket production-support endorsement.

Frontend declares Next ^15.1.7, React/ReactDOM ^19.0.0, TypeScript ^5.7.3 and includes package-lock.json. Actual lock versions are recorded in runtime-manifest.json; packages were not successfully installed. Do not claim a frontend version was run. Upgrade decisions require security/compatibility testing in M1, not an unverified major rewrite. Legacy Dockerfile still installs requirements.txt lower bounds and compose still uses mutable image tags; the release build must be switched to validated pins/digests in M1. PostgreSQL16.2 here is a disposable baseline binary, not recommended production patch level.

## Existing implementation inventory

- FastAPI main.py registers health, workspace, brand, persona, source/evidence, video, avatar and media-asset routers. Requests operate synchronously. No OIDC, cookie-session, membership/grant, CSRF, job202, immutable approval or v6 API implementation exists.
- Fourteen tables: workspaces, users, brands, personas, research_sources, evidence_items, avatar_profiles, video_projects, video_scenes, render_jobs, media_assets, clips, audit_logs, cost_ledger. IDs are string UUIDs, timestamps predominantly naive, money/clip seconds floats. See exact columns/FKs in schema snapshot.
- init_db creates vector extension and calls create_all at app startup. No Alembic history or additive migration proof. Application startup also owns the asyncio scheduler.
- UI routes: root/workspace bootstrap, videos and detail, personas, sources, review. No client membership portal, calendar or universal content library. Workspace key is stored in localStorage; this is not individual identity.
- Storage supports local placeholder and S3 boundary; it is not quarantined resumable upload, scan clearance or audited private-object lifecycle.
- Avatar, assembly, B-roll, clip and YouTube adapters simulate work or contain TODO stubs. HeyGen/Shotstack/YouTube configured branches explicitly still return simulated=true. Apparent local/remote URLs do not establish playable/live output. AI has a configured outbound path; all test runners disable its credentials. No provider was tested live.
- Default settings: development, SQLite, simulated video engines, local storage and float spending cap 25. These legacy values are NOT approved v6 defaults. v6 live budget must be zero until explicitly authorized.
- Deployment artifacts: python:3.12-slim Dockerfile, pgvector:pg16 and Redis7 compose, default local database password; not a production secret configuration. No operational logs, backups, real rows, account ownership or hosted endpoint inspected.

## Priority defects and preservation decisions

1. spend.py uses `workspace.spend_limit_usd or settings.spend_limit_usd`, so zero falls back to a nonzero default. Floating balance checks are non-atomic; cost is recorded after adapter work in the pipeline. M1 must introduce pre-dispatch reservations and zero-hard-block semantics.
2. Workspace keys identify tenants, not humans. Ordinary single-ID FKs allow inconsistent tenant references. New identity authority must not come from a legacy email string or key.
3. Scheduler queries all queued jobs without row claims/fencing; Redis failure returns true. A workspace-key authenticated jobs/tick request can run the global scheduler. Remove this surface from production; dedicated workers must enforce the originating authorization.
4. publish_video selects the latest assembly media in the workspace rather than binding exact approved asset/rendition version for the requested video. v6 replaces this dispatch authority with immutable publication revisions.
5. Scene replacement destroys prior scene rows; approval/version lineage and locked component reuse do not exist.
6. Simulated spend and publication-looking URLs are stored without the v6 provenance separation. Import as SIMULATED or UNKNOWN quarantine; never relabel old rows as live provider spend/publications.
7. Legacy tests call drop_all and accept an inherited DATABASE_URL via setdefault. Safe M0 helpers force a disposable local DSN, empty configuration and disabled dotenv before application imports. Do not run original pytest directly in an operational environment.

Target correction is additive cos_v6 schema plus explicit legacy mappings, not a destructive rewrite. Preserve reusable routers/UI/adapters as migration inputs, not as certification. Owner/brandless/unknown timezone records remain unclaimed or quarantined until proof. Detailed design and migration verification are in docs/DATABASE_DESIGN.md and docs/MIGRATION_PLAN.md.
