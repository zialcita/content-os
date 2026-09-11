# Proposed additive migration plan — M0 to M1+

**Status: design only. No migrations, backfills, production writes, provider calls or migration tests were executed by this document.** Target schema and normative API/DB mappings are in [DATABASE_DESIGN.md](DATABASE_DESIGN.md#412-normative-apidatabase-alignment-and-sql-enforcement); rationale in [ADR 0002](adr/0002-data-and-workers.md). This plan preserves the existing `public` schema, string IDs, historical media/jobs/costs and simulated results. It is not permission to delete data or invent owners.

## 1. Baseline and migration authority

Source inspected at commit `d3e3f9934681dcb29e65194f9699566165ccd813`, branch `engineering/v6-m0-foundation`. `entities.py` defines workspaces, users, brands, personas, research_sources, evidence_items, avatar_profiles, video_projects, video_scenes, render_jobs, media_assets, clips, audit_logs and cost_ledger. IDs are strings; workspace-local users are not authenticated global identities; timestamps lack timezone; spend and clip bounds are floats. No Alembic revision or deployed schema evidence is established by this inspection. `database.init_db()` still calls `create_all`; pipeline calls providers before transaction commits and replaces scenes destructively. Legacy scheduler must not run beside the new durable dispatcher for the same operation.

Before any implementation backfill, record actual DB engine/version, deployed code SHA, schema DDL/checksum, row counts, largest tables, string-ID validity, orphan/tenant-mismatch inventory, timestamp semantics, object availability and backup restore evidence. The checked-in model is not proof of production schema. Record all mutations by migration run ID, actor and exact code/checksum. Use a disposable PostgreSQL clone first. No real account connection, invitation, paid call, publication, or owner grant is part of database migration.

## 2. Preservation mechanism

Create `cos_v6` alongside `public`; target names in the design are schema-qualified. This avoids destructive renames and lets the old code continue to understand its original tables until explicitly fenced. After cutover API/worker connections use explicit schema qualification, not a surprising search_path change. Alembic manages only the intended schemas and migration history.

### 2.1 Migration control tables

All control tables are new; importer has a separate least-privilege database role. API roles cannot mark quarantine verified.

| Table | Minimum proposed columns / invariants |
|---|---|
| migration_runs | `id uuid PK`, `source_database_fingerprint text`, `source_commit text`, `migration_code_hash bytea`, `started_at timestamptz`, `finished_at timestamptz?`, `status text`, `operator_reference text`, `manifest jsonb` |
| legacy_id_map | `source_namespace text`, `entity_type text`, `legacy_id text`, `target_id uuid`, `legacy_workspace_id text?`, `run_id uuid`, `source_row_hash bytea`, `state text`; PK(source_namespace,entity_type,legacy_id), UNIQUE(source_namespace,entity_type,target_id). Source namespace identifies database+schema, not just table name. |
| legacy_rows | `source_namespace,entity_type,legacy_id` key; `raw_snapshot jsonb`, `raw_hash bytea`, `captured_at timestamptz`, `run_id`, `sensitivity_class text`; append-only revisions when source changes. Access restricted, secrets encrypted/redacted separately, no plaintext key export. |
| migration_issues | `id uuid`, `run_id`, `source_namespace,entity_type,legacy_id`, `issue_code text`, `details jsonb`, `state text`, `resolution_reference text?`, `resolved_by text?`; unique open issue fingerprint. Human decisions append history. |
| legacy_user_claims | `id uuid`, `legacy_user_map_id uuid` or full map key, `candidate_global_user_id uuid?`, `verified_identity_id uuid?`, `verification_method text?`, `proof_reference text?`, `verified_by_operator text?`, `verified_at timestamptz?`, `state text`; claimed identity is not assigned from email equality. |
| legacy_brand_assignments | map key, `target_workspace_id uuid`, `target_brand_id uuid?`, `basis text`, `authorized_by_membership_id uuid?`, `proof_reference text?`, `state text`; ambiguous/missing brand stays unassigned. |
| legacy_execution_quarantine | map key, `execution_class text` (SIMULATED/UNKNOWN/VERIFIED_LIVE), `reason text`, `remote_identifier text?`, `raw_url text?`, `evidence_reference text?`, `reviewed_by text?`; verified-live classification requires independent evidence. |
| migration_watermarks | `run_id,entity_type` key; `snapshot_position text`, `change_position text?`, `copied_count bigint`, `verified_count bigint`; progress is not completeness evidence without source reconciliation. |
| migration_reconciliations | `run_id,check_name,scope_key` key; expected/actual count or checksum, result, query hash, evidence path, executed_at; no fabricated passing rows. |

`legacy_id_map` is an import lookup, not the target version registry and not valid as an approval or job dependency target. Validate each target_id against its concrete target table in reconciliation. All application references use actual FKs. Non-inferable imports can have a mapping reserved without an active target row, with `state='QUARANTINED'`; counts explicitly distinguish mapped vs materialized vs verified.

Generate **fresh UUIDs for every target identity** and retain every original string verbatim. Do not assume a UUID-looking string is globally collision-free across entity classes. Mapping by source namespace+table+string preserves even malformed IDs. Once created, never regenerate a target UUID on rerun. Expose old IDs only via an authorized compatibility resolver scoped to current tenant; resolving an old ID does not grant access. No ALTER COLUMN USING id::uuid across live tables.

### 2.2 Identity and ownership — no email-based merge

1. Copy each legacy users row into restricted archive/mapping with original workspace/email/name/role and issue status. Create a distinct `users` placeholder in `UNCLAIMED` state if needed for migration bookkeeping, with **no user_identity and no active privileges**. Never coalesce users with equal email strings across workspaces.
2. Create corresponding membership records in `PENDING_VERIFICATION` with an empty effective roles set; keep reported legacy role in provenance, not executable owner authority. A legacy `role='owner'` default is evidence of old state, not proof of ownership.
3. Set imported workspace `state='LEGACY_UNCLAIMED'`, `owner_membership_id=NULL`. Brand/content is inaccessible to ordinary new users until an authorized claim/onboarding process validates the tenant. Existing workspace API key may continue only under a separately approved restricted legacy access policy; it cannot create ownership or approve/publish.
4. Owner claim requires verified OIDC `(issuer,subject)` plus independently authorized proof of legacy workspace control reviewed by an authorized operator/customer representative. Record proof reference and audit. Matching a verified email **alone** is insufficient. Possession of the old shared workspace key alone does not prove which person should own the workspace. Unresolved workspace stays quarantined/read-only; do not guess Martin or a Tailor Law reviewer identity.
5. After proof, link the exact legacy placeholder user to that global verified identity or perform an audited explicit account merge. If several legacy rows belong to one verified person, retain all old mappings, remap memberships in a transactional merge with conflict review; do not destroy duplicate provenance. Keep decisions/audit attributed to original unknown actors when no human identity was recorded.
6. Explicit owner action sets roles and brand grants for verified members. Non-owner admin still needs per-brand grants. Ownership transfer uses target acceptance and active same-workspace membership; an admin cannot grant ownership to themselves. Imported `actor='human'` audit strings never become a real approval_decisions actor.

No seed process creates users or invitations for AI Marketing Box/Tailor Law. Those names may be authorized workspace labels, not identity selectors.

## 3. Ordered stages, gates and rollback boundaries

### Stage 0 — Preflight / safe snapshot

- Stop or network-fence all paid/publication dispatch in the rehearsal environment. Confirm test DB name/host is disposable and not inherited production DATABASE_URL. Back up DB and referenced object inventory; restore into a separate environment with provider egress disabled.
- Capture unmodified source snapshots and object references with manifest hashes. Secret fields must not enter general evidence logs. Count all old tables, including scenes reached through video IDs.
- Detect cross-tenant references, dangling IDs, source-less evidence, reused emails, no-owner/multiple-owner records, blank/duplicate scene positions, nullable brands, invalid clip ranges, nonfinite monetary floats, apparent live URLs, and missing files. Classify issues without fabricating repairs.
- Establish old timestamp timezone semantics with deployment evidence; naive timestamp cannot simply be declared UTC. If unknown, preserve raw value and quarantine timeline-dependent facts with `TIMEZONE_UNKNOWN`.
- Gate: source manifest reproducible, restored clone available, owner/brand ambiguity catalogued, rollback backup retrievable. No data mutation until authorized environment is identified.

### Stage 1 — Expand (M1 foundation)

- Introduce Alembic tooling and revision chain, separate `cos_v6`, control tables, identity/membership/grants and typed registry foundation. Catalog later slice tables before allowing writes to those feature types. Each enabled kind must have subtype, reverse-existence constraint, immutable-child rules and tests; do not expose orphan registry kinds.
- Add UUID columns/maps and typed target tables, not replacements for legacy IDs. Any optional helper FK added to old tables starts nullable, preserving old writer compatibility. Prefer maps to intrusive legacy schema changes.
- Create tenant composite unique keys before FKs. For large tables use `CREATE UNIQUE INDEX CONCURRENTLY` outside transaction, then attach named UNIQUE constraint where supported. PostgreSQL FK targets must be a suitable nonpartial unique key. Add FK/CHECK `NOT VALID` where supported, then validate later; new writes still checked. NOT NULL and unique constraints need separate compatible staging, not imaginary `NOT VALID` syntax.
- Enable asset registry kind with SCRIPT universal asset type and shared-PK immutable script_versions extension (no script kind); enable voice_sample/clip_selection only alongside stable voice_samples/clip_selections aggregates, concrete version subtypes and reverse/seal checks. Seed exact scopes asset/narration, voice_sample/brand_voice, clip_selection/clip_selection, rendition/final_media; narration additionally type-checks SCRIPT.
- Add immutable registry/subtype deferred triggers, role restrictions/RLS, ownership routines, zero-default budget tables, outbox/inbox, fencing routines and indexes. Add preproduction_authorizations, immutable exact-input and one-job bindings, owner/admin-only cap approval and append-only revocations before any paid pre-plan endpoint is enabled. Never backfill spending permission.
- Build production_jobs as W-root with scope_type BRAND/WORKSPACE, purpose/job-kind/operation allowlist. WORKSPACE ADMIN export/delete allows NULL brand/campaign only with validated resource policy. Propagate real W same-job FKs and null-safe scope checks through work_authorizations, steps, attempts/observations, reservations, usage and inbox/outbox. B references retain non-NULL reference brand and B composite FKs; no nullable-FK bypass or synthetic administrative brand. Revoke mutation privileges before turning on reads/writes. A migration role is not an application role.
- New app version checks schema version; old startup `create_all` must not touch new tables. Do not simultaneously enable the unsafe old scheduler and new claims. Establish workspace migration gate/fence state before dispatch rollout.
- Gate: upgrade/downgrade rehearsal of empty new schema, PostgreSQL constraints/RLS tests, no legacy row changes, no enabled paid or publication path. Before new v6 writes only, rollback may disable the new feature and discard **empty** scaffolding if authorized. Never drop copied history simply because it is technically additive.

### Stage 2 — Backfill / deterministic transform

- Use repeatable snapshot plus change capture, or a documented maintenance window. A source `updated_at` alone is insufficient because many tables lack update timestamps and scene deletion loses rows. Proposed pilot default: bounded maintenance window to freeze legacy mutations, final snapshot and backfill; use CDC only if measured downtime requires it and its delete coverage is tested.
- During long rehearsal copy in batches, each row mapped by unique natural import key and source hash. Commit per batch; watermarks support restart. `ON CONFLICT` on map never overwrites a prior target UUID. If source content changes, create new imported version or conflict issue, not UPDATE a sealed version.
- Order: workspace maps → unclaimed users/memberships → brands/grants pending proof → media/source identities and snapshots → personas/profile snapshots → campaign/package/asset/video snapshots with established brand → scenes/clip lineage → archived jobs/usage/publication quarantine → audit/events. New registry construction and seal routines remain in force for imports; no disabling FK/trigger checks to load bad data.
- Inactive import roles/provenance permit no actor user where genuinely unknown; human decisions are **not** backfilled from status strings. Do not mint approvals for previously "approved" videos.
- Imported content that cannot satisfy active domain constraints stays in `legacy_rows`/issues with preserved objects. The conservation equation is source rows = safely materialized + explicitly quarantined, with every row mapped once; success is not defined as forcing all rows into active production tables.
- Gate: idempotent rerun, no changes to original IDs/content, exact conservation report per table, no unreviewed permissions or live spend, imported graphs valid. Rollback is read routing back to legacy with v6 fenced; keep backfill and mapping for forward repair.

### Stage 3 — Validate / shadow read

- Validate all staged FKs and CHECKs, prove no unsealed registry/subtype holes, graph cycles, cross-tenant references, unknown identity privilege, pointer-to-wrong-aggregate or simulated-live classifications. Compare source and target+quarantine totals/hashes.
- Run shadow reads through new authorization model using authorized local fixtures. Compare known legacy fields and report differences rather than requiring unsafe old behavior. Private object GET/signed URL tests must not leak another tenant's match.
- Rebuild budget counters from immutable allocations and compare. Verify imported amounts separately from authorized live balance. Do not choose legacy workspace float total over item ledger silently; differences become reconciliation issues.
- Validate startup no longer performs uncontrolled schema DDL for the cutover deployment. Test upgrade both from empty DB and from real-schema-shaped clone; stopping/restarting midway resumes correctly.
- Gate: owner claim decisions and brand assignments complete for workspaces being activated, all enabled schema constraints validated, all mandatory fixture tests pass with saved evidence, operational rollback and restore drill complete. Unclaimed workspaces can remain quarantined; do not activate them to meet a milestone count.

### Stage 4 — Cutover / controlled activation

- Announce maintenance/read-only interval. Stop old API mutations and scheduler; fence old credentials/DB role and provider egress for dispatch. Drain known work; classify **every outstanding legacy job** as completed historical, cancelled before send with proof, or unresolved quarantine/reconciliation. Never auto-replay old QUEUED jobs on v6.
- Final delta capture and checksum reconciliation, then a **single writer** per workspace. Prefer feature-gated routing by workspace; no asynchronous dual authoritative write to old and new schemas. If temporary dual-write is essential, one DB transaction writes both and only for lossless fields; avoid for immutable versions/approvals/publication history, which legacy cannot represent.
- Enable v6 reads and local writes for verified workspaces after auth/grant checks. Make old tables read-only, retaining compatibility ID resolution. Live budget remains zero until explicit new owner/admin cap authorization. Pre-plan voice preview/research/transcription/package drafting/plan proposal requires its immutable capped preproduction authorization (exact actor, operation, logical operation, inputs/hashes, workspace/brand, optional campaign/job, expiry); production still requires exact approved package/plan. No imported/default/hidden allowance. Provider/scheduler flags stay disabled until dependent real-provider gates and permission are satisfied.
- Recheck rows queued during deployment using epochs, grants, exact approvals and fresh fencing; uncertain operations stay RECONCILING. No mode fallback or historical auto-publication.
- Gate: smoke tests, isolation and scheduled/worker recovery tests, monitored backlog, inventory of active writers, audit of permission activation. M1 schema cutover does not establish M2–M6 completion.

### Stage 5 — Retain / eventual contract (not M0 authorization)

Legacy tables remain read-only until retention, exports, object recovery, business use and audit reconciliation are accepted. Remove legacy application paths only in a later review. Any physical purge follows approved retention and deletion workflow, not an Alembic downgrade. Shared links, ownership proofs and provider exceptions must remain discoverable for their required retention. A rollback to legacy cannot represent new v6 history; forward repair is the default once new writes occur.

## 4. Concrete per-table transformation policy

| Legacy input | Target handling | Uncertainty / preservation rule |
|---|---|---|
| workspaces | UUID map; new workspace initially LEGACY_UNCLAIMED; original name and key hash retained with restricted credential record | Old `spend_limit_usd=25` or configured fallback does not authorize new positive live spend. No owner guessed. |
| users | Separate unclaimed global placeholder and pending membership per legacy row; proof-based claim later | Same email never auto-merges; legacy role owner does not grant ownership. |
| brands | Preserve voice/guidelines as initial brand_profile version under same mapped workspace | Profile policy marks imported/unreviewed; no designated reviewer invented. |
| personas | Brand-local persona/version when original brand proven in same workspace | NULL brand remains pending authorized assignment. No default-brand guessing. |
| research_sources / evidence_items | Mapped source_asset/source_version and evidence snapshot when tenant/brand assignment and retrieval provenance suffice | URL/title alone is imported unverified reference, not fetched/supported evidence. Do not invent retrieval time/content hash. |
| avatar_profiles | Preserve raw provider/settings; new disabled profile only once brand/consent verified | Unknown consent blocks paid/render use. Simulated provider remains simulated. |
| media_assets | Preserve logical media identity plus immutable media snapshot/object reference; establish explicit brand assignment | Existing media file != universal asset. URI/title do not prove hash, media integrity, ownership or video lineage. Unknown/simulated objects quarantined. |
| video_projects | If brand consistent, create universal assets(MAIN_VIDEO) and separate assets(SCRIPT), initial asset_versions with script_versions sharing each SCRIPT version PK, plus video_project link via map | Missing package/plan inputs: retain legacy imported snapshot in quarantine until a reviewed package with genuine references is constructed; do not fabricate package approval. New active asset_versions requirements still hold. |
| video_scenes | Copy surviving ordered scene snapshots under the shared-PK SCRIPT asset version, map A/B-roll references when tenant/brand valid | History already deleted by replace_scenes cannot be reconstructed; record limitation. No claim all past versions recovered. Duplicate positions require manual ordering resolution. |
| render_jobs | Archive provider/result/status/request identifiers; create terminal imported observations or isolated reconciliation work where justified | Do not enqueue as real work; model provider name isn't proof result live. Never invent accepted remote IDs. |
| clips | Map to CLIP asset plus stable clip_selections aggregate and independent clip_selection_versions with exact known final cut/rendition/package/timing; output binds selection/moment only when supported | Do not infer source cut from latest assembly/title; absent lineage stays quarantined. Convert finite seconds using Decimal policy and verify bounds after probe. |
| video_projects.youtube_video_id / published_url | Preserve original strings in publication quarantine and provenance | No direct conversion to PUBLISHED. SIMULATED stays simulated; unknown is UNKNOWN, not live. Real verification attaches separate evidence without rewriting old apparent result. |
| audit_logs | Immutable archive plus minimized target audit import event; retain raw actor/entity labels | actor='human' cannot name a verified approver. Target audit label need not become valid subject FK. |
| cost_ledger / workspace spend | Preserve raw floats and per-row normalized historical amounts in LEGACY/UNKNOWN or SIMULATED provenance records | Never label real provider cost from provider name alone; independently reconcile provider records before VERIFIED_LIVE dimension. Do not insert duplicate charge from both workspace total and detailed ledger. |

Legacy branch-local records lacking a brand may remain in migration quarantine rather than creating a new unrestricted brand. A verified workspace owner may later authorize specific brand assignment, preserving original unassigned status in provenance. Do not automatically pick the first brand, "Standalone", or a brand from a filename.

### Fixed-value transformation rules

- Customer credits are signed integer units with SQL NULL currency, never invented USD or Money. Historical money remains the money dimension; do not relabel it as credits without genuine unit evidence. API credit entries/events expose credits, not fabricated monetary fields.
- Monetary conversion uses decimal representation of the stored/exported float (`Decimal(str(value)) * 1_000_000`, round-half-even to whole micros), recording original IEEE value/export text, rounding policy and residual. Reject NaN/Infinity/overflow; do not coerce to zero. Monetary reconciliation must compare normalized per-entry totals and legacy aggregate, reporting residual differences. Settled real totals need provider evidence, not just arithmetic.
- Clip seconds use decimal→milliseconds with a documented rounding policy and retain original seconds. Reject negative/reversed/nonfinite ranges. Verify against actual source duration and frame rounding later; migrated numeric values alone do not certify a playable clip.
- Naive timestamps are converted only after source timezone confirmed. Store raw value and conversion basis; otherwise quarantine any scheduling interpretation. Do not manufacture local schedule intent from a created_at timestamp.
- Hash existing private bytes only when permitted and retrievable; imported absent hash remains unknown/quarantined. A URI hash is not a media content hash. Migration does not fetch private provider URLs or incur cloud/provider costs without permission.

## 5. Proposed SQL checks and reproducible fixtures

The following are **queries and test specifications to implement/run**, not evidence of execution. All target names assume design migrations exist. Store command, PostgreSQL version, migration SHA, fixture seed, exit status, query output and relevant row/transition snapshots under acceptance evidence when run. Use transactions and savepoints to verify expected constraint violations without aborting all cases.

Cross-document gate: compare API subject/registry/scope metadata and exact identity fields to DATABASE_DESIGN §4.12 and ADR 0002. Wire APPROVED/REJECTED map to DB APPROVE/REJECT; OWNER is a workspace pointer, never a grantable stored role. Reject registry kind script and narration approval without SCRIPT type. Regenerate/check API artifacts in the API task, not by migration DDL; no drift waiver. Timeline input/output hash semantics and customer-credit union must be included. The SQL below is proposed only, not an assertion that these tables/routines exist.

### 5.1 Read-only source inventory examples

```sql
-- Run on authorized snapshot/clone; identifiers remain strings.
SELECT 'video_brand_cross_tenant' AS issue, v.id
FROM public.video_projects v JOIN public.brands b ON b.id=v.brand_id
WHERE v.workspace_id<>b.workspace_id;

SELECT 'scene_media_cross_tenant' AS issue, s.id
FROM public.video_scenes s
JOIN public.video_projects v ON v.id=s.video_id
JOIN public.media_assets m ON m.id=s.aroll_asset_id
WHERE m.workspace_id<>v.workspace_id;
-- Repeat for broll_asset_id and all other existing FKs, including clip asset/video.

SELECT workspace_id, count(*) AS legacy_owner_rows
FROM public.users WHERE role='owner' GROUP BY workspace_id;
-- Count only, never an ownership selection algorithm.

SELECT email, count(DISTINCT workspace_id) AS workspaces
FROM public.users GROUP BY email HAVING count(DISTINCT workspace_id)>1;
-- Sensitive output remains restricted; not an identity merge instruction.

SELECT id,workspace_id,youtube_video_id,published_url,status
FROM public.video_projects
WHERE status='published' OR youtube_video_id<>'' OR published_url<>'';
-- Classify all hits; no hit is assumed live.
```

### 5.2 Target integrity/reconciliation examples

```sql
-- No committed construction rows.
SELECT id FROM cos_v6.version_registry WHERE sealed=false OR sealed_at IS NULL;

-- Example reverse-subtype hole check, repeated for EVERY enabled kind.
SELECT r.id FROM cos_v6.version_registry r
LEFT JOIN cos_v6.asset_versions a
 ON (a.workspace_id,a.brand_id,a.id)=(r.workspace_id,r.brand_id,r.id)
WHERE r.kind='asset' AND a.id IS NULL;

-- SCRIPT extension totality/type integrity, not a second registry kind.
SELECT v.id FROM cos_v6.asset_versions v
JOIN cos_v6.assets a ON (a.workspace_id,a.brand_id,a.id)=
                       (v.workspace_id,v.brand_id,v.asset_id)
LEFT JOIN cos_v6.script_versions d ON (d.workspace_id,d.brand_id,d.id)=
                                     (v.workspace_id,v.brand_id,v.id)
WHERE (a.type='SCRIPT') IS DISTINCT FROM (d.id IS NOT NULL);
SELECT id FROM cos_v6.version_registry WHERE kind='script'; -- always zero
-- Independent sample/selection subtype existence; wrong-kind and aggregate ownership
-- also tested by FKs/deferred validators, not just these anti-joins.
SELECT r.id FROM cos_v6.version_registry r
LEFT JOIN cos_v6.voice_sample_versions v
 ON (v.workspace_id,v.brand_id,v.id)=(r.workspace_id,r.brand_id,r.id)
WHERE r.kind='voice_sample' AND v.id IS NULL;
SELECT r.id FROM cos_v6.version_registry r
LEFT JOIN cos_v6.clip_selection_versions v
 ON (v.workspace_id,v.brand_id,v.id)=(r.workspace_id,r.brand_id,r.id)
WHERE r.kind='clip_selection' AND v.id IS NULL;

-- W-root execution: NULL brand must never skip parent/context validation.
SELECT s.id FROM cos_v6.job_steps s
LEFT JOIN cos_v6.production_jobs j
 ON (j.workspace_id,j.id)=(s.workspace_id,s.job_id)
WHERE j.id IS NULL OR j.scope_type<>s.scope_type OR j.purpose<>s.purpose
 OR j.job_kind<>s.job_kind OR j.originating_operation_id<>s.originating_operation_id
 OR j.brand_id IS DISTINCT FROM s.brand_id
 OR j.campaign_id IS DISTINCT FROM s.campaign_id;
-- Repeat for attempts, authorizations, reservations, ledger and job events.
SELECT j.id FROM cos_v6.production_jobs j
WHERE j.scope_type='WORKSPACE' AND
 (j.brand_id IS NOT NULL OR j.campaign_id IS NOT NULL OR j.purpose<>'ADMIN'
  OR NOT ((j.job_kind='WORKSPACE_EXPORT' AND j.originating_operation_id='requestWorkspaceExport')
       OR (j.job_kind='WORKSPACE_DELETE' AND j.originating_operation_id='requestWorkspaceDeletion')));

SELECT id FROM cos_v6.usage_ledger
WHERE (ledger_dimension='CUSTOMER_CREDITS' AND (currency IS NOT NULL OR unit<>'credits'))
 OR (ledger_dimension='PROVIDER_COST' AND (currency IS NULL OR currency !~ '^[A-Z]{3}$' OR unit<>'micros'));
-- Signed credit adjustments are valid, not negative-money validation errors.

-- Owner must be same workspace, active and verified, not merely non-null.
SELECT w.id FROM cos_v6.workspaces w
LEFT JOIN cos_v6.workspace_memberships m
 ON (m.workspace_id,m.id)=(w.id,w.owner_membership_id)
LEFT JOIN cos_v6.users u ON u.id=m.user_id
WHERE w.state='ACTIVE' AND
 (m.id IS NULL OR m.state<>'ACTIVE' OR u.status<>'ACTIVE' OR u.verified_at IS NULL);

-- Simulated/unknown must not masquerade as live.
SELECT id FROM cos_v6.publications
WHERE state='PUBLISHED' AND
 (execution_mode<>'LIVE' OR verified_live_at IS NULL OR remote_id IS NULL);

-- Explicit counters: group by account; do NOT sum workspace+campaign+job together.
WITH expected AS (
 SELECT a.budget_account_id,sum(a.amount_micros) AS reserved
 FROM cos_v6.reservation_allocations a
 JOIN cos_v6.budget_reservations r
  ON (r.workspace_id,r.id)=(a.workspace_id,a.reservation_id)
 WHERE r.state='RESERVED'
 GROUP BY a.budget_account_id
)
SELECT b.id,b.reserved_micros,coalesce(e.reserved,0) AS rebuilt
FROM cos_v6.budget_accounts b LEFT JOIN expected e ON e.budget_account_id=b.id
WHERE b.reserved_micros<>coalesce(e.reserved,0);
-- Parallel check settled_micros against sum(usage_allocations.amount_micros).

-- Cycle check; UNION bounds revisits on finite graph.
WITH RECURSIVE reach(workspace_id,brand_id,src,dst) AS (
 SELECT workspace_id,brand_id,consumer_version_id,prerequisite_version_id
 FROM cos_v6.dependency_edges
 UNION
 SELECT r.workspace_id,r.brand_id,r.src,e.prerequisite_version_id
 FROM reach r JOIN cos_v6.dependency_edges e
 ON (e.workspace_id,e.brand_id,e.consumer_version_id)=
    (r.workspace_id,r.brand_id,r.dst)
)
SELECT DISTINCT workspace_id,brand_id,src FROM reach WHERE src=dst;
```

Expect zero rows on each invalidity query, but keep outputs when not zero and block activation. Additional checks enumerate `pg_constraint` validation state, all tenant-composite FKs, trigger enabled state and runtime role privileges. `SET CONSTRAINTS ALL IMMEDIATE` inside fixture transactions must surface deferred registry errors before commit. Run concurrent tests in separate actual PostgreSQL connections, never an in-memory mock.

### 5.3 Fixture matrix and expected persisted evidence

| Fixture / action | Expected state and verification |
|---|---|
| Two workspaces A/B, each two brands; UUID and malformed old IDs | All original strings round-trip through maps. Same legacy string across entity types/databases stays distinct. Cross-workspace/brand parent reference raises FK violation; same-brand valid reference succeeds. |
| Same email in A/B, legacy owner defaults, no proof | Two separate pending identities/memberships; no ACTIVE owner, grants, verified OIDC identities or invitations. Legacy workspace key cannot approve or claim owner. |
| Verified local fixture users with owner/admin/editor/reviewer/publisher/viewer roles | Editor approval and publisher content edit denied; admin without brand grant cannot read content. Admin cannot transfer owner/self-promote. Owner transfer checks same-tenant target/acceptance; owner revocation rejected while workspace ACTIVE. |
| Fake registry UUID with no subtype; wrong subtype; unsupported review kind/scope | Deferred commit fails; typed FK/scope constraint fails. Insert subtype without registry fails. Insert/update/delete child after sealing fails. No orphan review subject can persist. |
| SCRIPT identity, extension, role and scope | SCRIPT is an assets row with one asset registry/version ID and immutable script_versions same PK; reject non-SCRIPT extension, missing extension, kind=script, wrong script subject/asset and script-scope approval on ordinary asset. asset/narration remains distinct from final_editorial. Owner/admin/reviewer with grants may review; editor-only cannot. |
| VOICE_SAMPLE / CLIP_SELECTION before output | Stable sample_id/selection_id and independent sealed version registry rows persist before production; wrong aggregate current pointers and cross-brand subjects fail. Editing sample/moments creates new version, no approval inheritance. No fake produced clip asset needed to approve selection. |
| Exact RENDITION/final_media | Approve via rendition decision endpoint; both subject IDs equal path rendition_id. Wrong rendition or asset final approval alone fails dispatch; publication requires exact valid final_media plus asset/publication decisions and technical validation. |
| Pre-plan paid voice/research/transcription/package/proposal | With owner/admin-approved immutable authorization and all explicit caps, one matching operation can reserve without plan; mismatched actor/operation/logical operation/inputs/hash/brand/campaign/job, expiry/revoke, absent account or zero cap blocks before intent. Reviewer-only/editor-only cannot grant cap. Concurrent redemption binds at most one job. New inputs or undeclared repair require new authorization. |
| Production cannot reuse preproduction permission | Render/generation/regeneration requires exact approved package/plan and full cap set; substituting preproduction ID/purpose or ADMIN scope fails. Remaining authorization amount cannot silently fund unrelated work. |
| W-root administrative execution through accounting | Owner workspace export/delete creates scope_type WORKSPACE, purpose ADMIN, exact allowed job kind/operation, NULL brand/campaign. Step/attempt/auth/reservation/ledger/outbox/inbox retain W same-job FKs and null-safe context checks. Non-owner owner-only request, arbitrary NULL-brand production, cross-job attempt, wrong campaign or B reference without explicit validated brand scope fails. Stale lease cannot commit administrative output/accounting/event. Paid admin needs explicit scoped work authority and caps, never hidden budget. |
| Timeline input vs output | Request base_asset_version_id is existing sealed project asset version; server atomically creates timeline, distinct output asset_version_id and binding plus ETag CAS/invalidation/outbox. Wrong project/base or stale ETag rolls everything back. Timeline hash includes base/actual inputs, excludes output binding; graph has output→timeline→base, no reverse output edge. |
| Credits and money separation | Positive/negative CUSTOMER_CREDITS amount_units persist with unit=credits and currency NULL; USD/zero-money substitution fails. PROVIDER_COST requires micros+ISO currency; signed adjustments allowed. Credit entries cannot change money-account counters; API/event credit union has no Money amount. |
| Same-brand asset X current pointer set to Y's version | Owning-aggregate composite FK fails despite matching brand. |
| Two simultaneous edges A→B and B→A | Brand graph lock serializes; second reachability check fails. Multi-hop/batch self-cycle rejected. READ COMMITTED read after lock sees committed predecessor. |
| Package→asset→rendition→publication; package revision | New package snapshot; reverse invalidation records; affected unpublished schedule PAUSED; unrelated locked scene/text asset untouched; live publication unchanged plus correction review. |
| Transcript correction at clip boundary | Original spoken text/times preserved, correction version + segment_lineage present; misalignment blocks render until valid confirmation. Clip source final cut/rendition/package composite FKs reject wrong cut. |
| Two budget workers, each reserve 80, remaining 100 | Exactly one succeeds; second BUDGET_EXCEEDED; counters=80 not 160. Repeat same operation returns same reservation. Zero remains hard zero; missing account blocks. |
| Settle/release race and duplicate callback | One terminal reservation transition and one logical ledger entry; no lost counters; duplicate inbox no repeated settlement. Real overrun records truth and blocks next spend; simulated entries excluded. |
| Claim lease T1; expire; reaper T2; old worker returns | Token T1 cannot heartbeat, write child output, transition, settle or emit authoritative success. T2 reconciliation retains uncertain reservation. |
| Kill worker before intent commit / after commit before HTTP / after provider accepts before response | First safely queueable, latter two RECONCILING; no blind submit. Contract adapter records one logical operation. Actual provider billing semantics require separate authorized real test. |
| Two outbox relays, crash after send before mark; duplicate/out-of-order inbox | At-least-once message transport; one DB application and one settlement; preserve observation and no terminal regression. Hash mismatch flagged. |
| Metadata/account/timezone/schedule revision; ambiguous DST; >15 min late | New publication revision and required fresh decision, wrong-version approval rejected, DST correction demanded, late schedule PAUSED+notification. |
| Consent/grant revoked before dispatch vs after committed in-flight intent | First blocked with no authorized intent; second cancelled/reconciled where possible, race explicitly recorded, never falsely assert provider cancellation. |
| Legacy simulated/unknown PUBLISHED URLs | Raw URL/ID preserved in quarantine, zero new LIVE/PUBLISHED rows; no dispatch/ledger promotion on rerun. |
| Duplicate conversion external ID; unavailable metrics | One conversion `(workspace,source,id)`; unavailable is NULL with reason; cumulative metrics not summed. Cross-tenant optional attribution FKs fail. |
| Importer crash mid-batch and rerun | Same UUID maps, no duplicate snapshots/ledger/approvals, conservation counts/source hashes stable; changed source becomes new version/issue. |
| DB restore with v6 history and pending external intents | History/media refs/approvals survive; fence all workers and provider egress, reconcile pending known remote operations before enabling dispatch. Backup age never licenses duplicate submission. |
| Partial M1 code rollback after new version+ledger writes | v6 records retained and accessible via compatible read/recovery build; no downgrade drops. New writers stopped; operator chooses forward fix or read-only operation. |

Fixture names like A/B denote local synthetic accounts only. Do not create real Martin/Tailor Law identities as test fixtures. Fixture provider outputs clearly SIMULATED; none satisfy the real publication/media gates.

## 6. Honest rollback and disaster recovery

**Before cutover/no new authoritative writes:** disable new routes, stop new workers and leave legacy authoritative; keep mapping/backfill artifacts and investigate. Revert application code only if its schema compatibility is proven. Empty new scaffolding can be removed only by separate reviewed action, never automatic destructive downgrade.

**After any v6 write:** old code cannot represent immutable versions, approvals, multi-membership, reservation ledger or publication revisions. Therefore a simple Alembic downgrade or dropping `cos_v6` is **not** a safe rollback. Stop new mutations/dispatch, preserve v6 read access through a compatible recovery build, snapshot state and forward-fix. A compatibility projection may expose old readable fields but cannot become an authoritative writer or flatten/delete history. If business must resume on old UI, keep v6 as system of record and build an audited adapter for representable operations; block unsupported writes.

**After an external intent exists:** halt/fence dispatchers, retain reservations and remote/request keys, reconcile provider state before any resubmission. Rolling back the database does not roll back a social post or provider bill. Restore drills run with egress disabled and a new worker-generation fencing barrier; reconcile all possible post-backup intents from retained operation audit/provider records before activation. Record any unrecoverable operation ambiguity visibly rather than guessing.

**PITR/backup restore:** restore to a new instance, not overwriting the only current history. Compare recovered immutable ledgers/approval/publication data and object manifests to the latest preserved state. Replay verified events only through inbox/idempotency rules. Restore requires approved RPO/RTO and retention handling, not claiming zero loss. Proposed <=24h RPO / <=8h RTO remain unproven until drill. Never delete newly written paid, review or publication history to make a rollback look clean.

## 7. Unresolved implementation inputs

- Authorized source database inventory/size and snapshot/CDC requirements; timezone provenance and private object accessibility.
- OIDC provider/issuer and authorized legacy-owner proof process, actual global users, memberships, per-brand assignments and designated reviewers.
- Actual evidence distinguishing legacy simulated vs real provider transactions/publications; unknowns must remain quarantined.
- PostgreSQL hosting/version, migration maintenance window, backup/object restore strategy and reviewed retention limits.
- Canonical hash and version validators, security-definer/RLS integration and lock-order enforcement; these must have M1 PostgreSQL tests.
- Provider-specific idempotency, callback verification, cost finality and remote cancellation semantics. Positive live budgets and test publication authority remain separately required.

Until these gates are resolved, prepare schemas/tests and local fixtures only; do not label migration or R1 complete.
