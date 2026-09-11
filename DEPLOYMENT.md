# Deployment and recovery readiness — not a deployment authorization

M0 status: no production project, region, operational database, object store, OIDC client, TLS domain, backup or deployment has been inspected or created. Historical Dockerfile/compose are local scaffolding; a Render-ready sentence is not deployment evidence. Do not deploy the legacy runtime as a client pilot.

## Target topology

Same-origin Next.js web and FastAPI API, separately running Python workers/reconcilers, managed PostgreSQL, private S3/R2 storage and maintained OIDC. Redis optional, never job/budget authority. No required work depends on a live HTTP request. Owner must approve host/project/region/cost and data-processing terms before provisioning. Use secure platform secret configuration, non-owner/non-BYPASSRLS database runtime roles, private buckets, encrypted provider tokens and short-lived object capabilities.

## Release prerequisites

- Pinned supported runtime/dependency lockfiles and image digests, dependency/security review and passing frontend build.
- CI schema/unit/integration/frontend gates; disposable PostgreSQL migrations both clean and populated legacy fixtures; no startup create_all.
- Expand/backfill/validate/cutover migration checkpoints from docs/MIGRATION_PLAN.md, quarantined uncertain legacy identities/publications, signed owner migration authorization.
- Session/OIDC/CSRF/permissions tests, storage quarantine/scanner isolation, exact-version reviews, atomic caps, fenced workers, outbox/inbox, uncertain-outcome reconciliation.
- Real-provider capability/consent/budget/visibility evidence and both teams' editorial/UAT acceptance; AT01–30 and operational checks in docs/ACCEPTANCE_MATRIX.md.
- Separate production release approval, access to rollback artifacts, maintenance/cutover policy and on-call owner. Draft PR approval is not release authorization.

## Planned backup/restore verification (NOT RUN)

Daily encrypted database backups with catalog/checksum and access controls; object versioning/recovery consistent with approved privacy policy. Candidate RPO<=24h and RTO<=8h require owner agreement. Restore database and object references into a fresh isolated environment, with outbound paid/publishing adapters disabled. Verify record counts, immutable hashes, tenant roles/grants, approvals, media object existence, ledger reconciliation and migration version. Restore queued jobs in held state; reconcile previously submitted remote attempts before any resumption. Do not replay a published operation after restore. Measure actual restore wall time and recovered watermark. Store drill logs/manifest/reviewer in docs/evidence/m6 before claiming recovery readiness.

## Rollback posture

Before data cutover, stop new dispatch, preserve backups/manifests and revert only the deployment artifact after schema compatibility check. After v6 writes, do NOT drop cos_v6 tables or restore legacy write authority over newer histories. Preserve all versions, approvals, ledgers and attempt identities; favor forward fix or read-only degraded service. Uncertain provider submissions stay RECONCILING with reservations held. See migration plan for dual-read/write boundary and validated inverse steps. No rollback command here has been executed against operational data.

## Retention/deletion planning (NOT ACTIVATED)

Owner-approved policy required for originals/approved output retention, temporary cleanup, audit/usage minimization, active purge and backup expiry. Tombstone immediately stops work and dispatch; separate tracked purge handles private objects and provider exceptions. Never claim a provider deletion succeeded from a local tombstone. Defaults are planning only until approved; no destructive purge or takedown is authorized by this document.

## Required operating records before pilot

Host/project identifiers (no secrets), OIDC issuer/client configuration (no secret values), database version/role/migration inventory, bucket privacy/lifecycle proof, provider/app permissions and account IDs, budget caps, alert thresholds, exact deployment artifact, backup/restore evidence and incident ownership. All remain pending unless later evidence explicitly replaces this M0 status.
