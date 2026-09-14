# ADR 0002 — Tenant-safe immutable data and durable workers

- **Status:** Proposed (M0 design; not implemented or applied)
- **Scope:** PostgreSQL schema, identity/tenant ownership, immutable lineage/reviews, migrations, fixed-value budgets, durable execution and external side-effect safety.
- **Authority:** [Content OS v6 specification](../spec/CONTENT_OS_ASTRA_BUILD_SPEC_v6.md), §§3–4, 7–16, 18–21.
- **Companion contracts:** [Database design](../DATABASE_DESIGN.md), [Migration plan](../MIGRATION_PLAN.md), [API contracts](../API_CONTRACTS.md); normative field/role/registry/scope mappings in Database design §4.12.
- **Inspected checkout:** `engineering/v6-m0-foundation`, commit `d3e3f9934681dcb29e65194f9699566165ccd813`. No production database or deployment certification is inferred.

## Context

The repository has FastAPI/SQLAlchemy models with string IDs and workspace-local users, workspace key authentication, nullable brand IDs, floating-point money/clip timing, mutable video scripts/scenes and a rudimentary render-job/cost ledger. Startup uses `create_all`. The pipeline performs provider calls before commit, records spend after calling providers, and replaces scenes by deletion. Publication finds the latest workspace assembly rather than an exact version. Scheduler uses an in-process loop with best-effort Redis lock, continuing when Redis is unavailable. These observations come from reading `entities.py`, `database.py`, `auth.py`, `spend.py`, `pipeline.py` and `scheduler.py`, not from execution evidence.

v6 requires preserved records, verified global identities, explicit brand grants, typed immutable dependencies and reviews, exact publication revisions, zero-default authorized budgets and robust recovery when a provider may have accepted a call. A table of arbitrary UUID subjects or an internal idempotency flag cannot meet those requirements.

## Decision

### 1. PostgreSQL as the authoritative state machine

Use PostgreSQL, SQLAlchemy and Alembic in a modular application with separate workers. Redis is optional for non-authoritative caching/rate limiting only. Deployments migrate explicitly and check schema compatibility; no indiscriminate startup DDL. SQLite tests cannot establish concurrency/tenant safety. Use checked text status codes with allowed transition validation, optimistic lock versions, UTC timestamps, UUID target IDs, integer milliseconds, rational FPS and fixed micro-unit money.

Introduce additive `cos_v6` tables alongside current `public` tables. Keep legacy IDs and raw provenance via stable source-namespace/table/ID→UUID mappings. Prefer single-writer per-workspace cutover with a bounded maintenance window unless measured scale justifies tested CDC. Do not cast all string IDs in place, destructively rewrite existing tables, or dual-write asynchronously into two authoritative histories.

### 2. Identity, ownership and tenant boundaries are explicit

Global users authenticate via verified OIDC issuer+subject; email is contact data, not account-link proof. Pending legacy membership/owner claims remain inactive until authorized proof is recorded. Preserve old default roles as provenance, not new ownership grants. Workspace keys remain restricted credential principals and cannot impersonate a human reviewer or owner. Never infer Martin, client users or designated reviewers from names/emails.

Tenant-owned FK references include workspace and, for brand objects, brand. Current-version pointers include aggregate ownership too. Every non-owner, including admin, requires explicit brand access; role union does not remove tenant boundaries. Owner is a same-workspace active verified membership pointer, not an admin-grantable role string. Ownership transfer requires current owner authority and target acceptance. API/services enforce action roles; RLS and composite constraints are defense in depth. Sensitive mutation routines use fixed-search-path security-definer functions, narrowly granted privileges and verified actor context. Workers revalidate original work authorization before paid or publishing operations.

### 3. A total typed version registry, not loose polymorphic references

A `version_registry` holds immutable hashes/snapshots and a finite kind. Each enabled kind has exactly one concrete subtype. SCRIPT is a universal asset type: script_versions is an immutable extension sharing asset_versions PK, registry kind asset only (no independent script kind); deferred validation requires the extension exactly for SCRIPT assets. VOICE_SAMPLE and CLIP_SELECTION instead have independent voice_sample/clip_selection registry kinds, concrete voice_sample_versions/clip_selection_versions and stable voice_samples/clip_selections aggregates, not clip-output-only children. Composite FK with constant kind prevents mismatched subtype references; a deferred reverse-existence constraint prevents registry-only orphan subjects. All construction is transactional: unsealed registry + subtype + FK-bearing child rows/edges, validation/hash, sealing; unsealed rows cannot commit. After seal, subtype/children/edges are immutable, including new child insertion. Mutable status projections do not change snapshot content.

All reference-bearing JSON has a matching normalized FK projection validated at seal. Jobs and reviews pin real registry versions and allowed kinds/scopes. Decisions are append-only history, distinct from mutable pending review tasks. Publication approval binds the exact immutable revision including asset/rendition, destination account, metadata, tracking/visibility and resolved schedule. SCRIPT subjects map exactly to asset/narration and require SCRIPT type/extension; ASSET maps to asset/final_editorial, VOICE_SAMPLE to voice_sample/brand_voice, CLIP_SELECTION to clip_selection/clip_selection, RENDITION to rendition/final_media and PUBLICATION to publication_revision/publication. Rendition approval retains its exact API scope/decision endpoint and both IDs equal rendition_id; final asset approval or technical validation cannot substitute. Asset/media, narration, budget authority and publication approvals remain separate. Revisions never inherit old approval automatically.

Dependencies are typed consumer→prerequisite relationships constrained by a migration-owned allowlist. Serialize graph writers under a per-brand row lock acquired before READ COMMITTED reachability queries; reject self/multihop/batch/concurrent cycles. A trigger acquiring a lock after a stale query snapshot is not enough. Sealed dependencies and explicit reverse invalidations support targeted freshness updates; live publication history remains intact.

Avoid asset↔timeline cycles: request base_asset_version_id identifies the sealed input being edited and belongs to the stable project asset; timeline hashes that base and exact script/media inputs. Server atomically creates/seals a fresh timeline, a distinct output asset_version_id pointing to it and video_asset_bindings, with ETag current-pointer CAS/invalidation/outbox in the same transaction. Response asset_version_id is server-derived, not the request base; exclude that output binding from timeline canonical hash and prerequisite edges. Roll back the entire construction on conflict. Source/transcript segment lineage and final-cut clip references remain explicit; neither old media rows nor a transcript alone replace reviewed package/final-cut lineage.

### 4. Fixed money with atomic multi-cap reservations

Use signed bigint micro-units+ISO currency for PROVIDER_COST, never binary floats; CUSTOMER_CREDITS instead uses signed integer amount_units, unit=credits and SQL NULL currency, not a Money object, invented USD or implicit FX, with separate dimensions and explicit LIVE/SIMULATED classification. A live unconfigured budget is zero; old defaults are not new authorization.

Paid PRODUCTION requires exact approved package/plan, and reserves workspace/campaign/job plus approved-plan caps. Paid pre-plan voice preview/research/transcription/package drafting/plan proposal instead requires explicit immutable preproduction_authorizations approved by verified owner/admin (reviewer role cannot grant budgets): exact requesting actor, workspace/brand, optional campaign/job, originating/logical operation, allowed bounded substeps, canonical input hashes/versions, expiry and cap/currency. Normalize input references; one immutable redemption binds an authorization to a job. The input hash covers full normalized request and relevant If-Match/limits, excluding only its authorization ID; changed inputs/actor/operation/cap require a new authorization. Reserve workspace/job, campaign if present and authorization cap; zero/missing/revoked/expired/mismatched permission fails closed. Production cannot reuse this preproduction permission and no hidden budget or fake plan/campaign is created. Explicit non-production ADMIN/PUBLICATION operations require their own scoped work authorization and configured workspace/job/campaign-if-present caps; these cannot authorize production/research/render and publication still needs exact decisions. All branches reserve in one transaction with deterministic row-lock order. Same operation replay returns the same reservation. `RESERVED → SETTLED|RELEASED` uses CAS and immutable ledger entries; refunds/corrections are additional signed entries. Unknown remote acceptance retains funds. Actual cost overrun is recorded truthfully and freezes additional spend, not rejected from the ledger to keep a budget illusion. Budget counters are rebuildable from allocation/ledger rows, not independent truth. Do not sum hierarchical cap allocations as multiple provider expenses. Concurrency-slot allocation is separately atomic and lease expiry does not prove provider work stopped.

### 5. Durable jobs, fencing and at-least-once event delivery

Execution is **W-root**, not universally B: production_jobs uses scope_type BRAND/WORKSPACE plus purpose, checked job kind (API job_type) and originating_operation_id. WORKSPACE requires ADMIN purpose and only WORKSPACE_EXPORT/requestWorkspaceExport or WORKSPACE_DELETE/requestWorkspaceDeletion, with NULL brand/campaign and preserved owner-only resource authority. BRAND requires a real authorized brand; production requires campaign, permitted preproduction may omit it. Steps/attempts/work authorizations/reservations/ledger/outbox/inbox use real W same-job FKs and null-safe scope/context equality. Content references still require explicit non-NULL reference brand, B composite FKs and validated current actor/job brand scope; NULL is never all-brand permission or a MATCH SIMPLE FK bypass.

PostgreSQL job/step rows persist exact input versions, input hash, logical operation ID, submit attempt count, next attempt time, lease owner/expiry/heartbeat and monotonic fencing token. Claim runnable steps with `FOR UPDATE SKIP LOCKED` in short transactions. Renewal/result commit requires owner+token+unexpired lease+expected state; every child output, transition, settlement and authoritative outbox write shares that guard. An expired worker cannot commit just because it returned before the reaper.

Persist submission intent and reservation before a network call. A crash after intent commit, even with sent_at NULL, may represent accepted work. Reaper fences and routes that operation to RECONCILING, not blindly QUEUED. Safe retries require proven nonacceptance or verified provider deduplication semantics (including billing/window); default at most three safe submissions, separate from polls. Unknowable outcome requires operator resolution. Cancellation may still incur real cost and must preserve remote outcomes.

Business mutation and outbox insertion are atomic. Relay uses leased fenced claims; crash after delivery before acknowledgment can duplicate transport. Inbox uniqueness+hash validation and business application in one transaction deduplicate effects. Callback tenant is resolved from verified provider account/attempt, not untrusted payload tenant IDs; unknown callbacks are quarantined. No terminal regression from out-of-order callbacks and no duplicate settlement. External calls triggered by an event become durable intents, not actions inside an inbox transaction.

### 6. Explicit external ambiguity boundary

Database fencing protects local writes, **not already transmitted HTTP requests**. Final pre-send permission/lease check cannot eliminate the check-to-send race. Dispatch authorization commit is the point the operation enters the in-flight region. Revocation/schedule change afterwards blocks downstream work and requests cancellation/reconciliation; it does not promise that the provider did nothing. Only provider-enforced idempotency/cancellation can strengthen that guarantee. No new dispatch for the same logical publication while an earlier revision's remote acceptance is unresolved. Remote upload ID is not proof of live publication or correct visibility.

### 7. Preserve history through migration and rollback

Every legacy row is either safely materialized or explicitly quarantined with preserved provenance and original ID. Ambiguous brands, users, hashes, timestamps, lineage or provider outcomes are not filled with guesses. Apparent simulated/unknown publications remain outside verified live publication state. Historical "human" approval audit labels do not become invented user decisions. Existing surviving scenes can be preserved; previously deleted history cannot be reconstructed.

After v6 writes, old code cannot represent the new histories. Rollback means stop/fence new writes and dispatch, retain the schema/history, provide compatible read/recovery access and forward-fix. Do not drop newly written versions, approvals, reservations, ledger or publication records as a downgrade. A backup restore cannot undo provider side effects; disable egress and reconcile possible post-backup operations before dispatch resumes.

## Alternatives considered

| Alternative | Why not selected |
|---|---|
| In-place string→UUID ALTER and destructive model replacement | Cannot safely handle malformed/colliding legacy IDs, unknown relationships or old writer compatibility; loses rollback/provenance. |
| Email-based user consolidation and first-owner/default-brand assignment | Does not prove identity or ownership; can grant another person's data and publication authority. |
| Only API tenant checks and ordinary single-ID FKs | Workers, callbacks and future queries can make cross-tenant references; no database invariant. |
| `subject_type + subject_id` with no true FK | Allows orphan/mistyped review/dependency subjects. Registry without reverse-subtype enforcement has the same hole. |
| All data in generic JSON snapshots | Useful for content, inadequate for references, rights and scope constraints; normalized projections required. |
| Mutable approval boolean/status on asset/review row | Loses actor/history/scope and allows approval of changed content or a different publication schedule. |
| Redis lock/in-process scheduler as authority | Failure/restart permits duplicates or drops execution; lacks database fencing and durable intent. |
| Claim only job row and guard only final status update | Stale worker can still write child outputs/ledger; step-level fenced transaction required. |
| Hold DB locks across provider HTTP calls | Long locks/connection exhaustion; still cannot atomically commit with remote provider or solve lost response. |
| Blind retry after lease expiry or timeout | Provider may already have accepted/billed/published; internal idempotency does not enforce remote uniqueness. |
| Float cost counter / check after provider call | Races, rounding and hard-zero fallback; no preauthorized multi-cap reserve. |
| Drop new schema on downgrade after cutover | Deletes newly written business history and cannot undo remote spend/publication. |

## Consequences

- More explicit tables, constraints and construction routines; subtype additions require migrations/tests rather than adding arbitrary strings.
- Strong referential integrity is complemented, not replaced, by service authorization and media/provider validators. RLS testing must include pooled transactions and definer privilege boundaries.
- Brand graph serialization and deterministic lock ordering trade some write throughput for clear correctness; measure pilot dataset before optimizing. Large invalidations need fail-closed epoch barriers, not eventual unchecked dispatch.
- Immutable snapshots/observations consume storage. Retention/minimization/purge must be designed separately, with no accidental cascades.
- External ambiguity is visible as RECONCILING/WAITING_USER. Availability may be lower than reckless automatic retries; safety is intentional.
- Local fixtures and PostgreSQL tests enable M1 development without credentials or positive spend. They do not satisfy real-provider or R1 acceptance.

## Required validation before acceptance/implementation claims

Run the migration plan's PostgreSQL fixtures (including cross-contract mappings: wire APPROVED/REJECTED→DB APPROVE/REJECT, uppercase roles→checked lowercase roles, OWNER→owner pointer, DEVELOPMENT_SIMULATED→SIMULATED): SCRIPT shared-PK/type/narration and no script registry kind; independent voice/clip aggregates and versions; exact rendition final_media; bounded preproduction and production-no-bypass; W-root admin null-safe propagation through accounting/events; atomic timeline base/output/hash separation; signed credit NULL-currency; tenant/brand FK and role denial; owner transfer/revocation; orphan subtype/review rejection; immutable child insertion rejection; concurrent cycle prevention; wrong-aggregate pointer; multi-cap reserve and settle/release races; zero budget; old fencing token rejected across outputs/ledger/outbox; kill/restart at each external-call boundary; duplicate/out-of-order events; exact publication revision approval; consent revocation; additive import rerun; simulated publication quarantine; retention-safe rollback and restore. Record source SHA, DB version, fixture/action/expected state and artifacts. None of those tests are asserted as run here.

## Open gates

Actual database size/schema/timezone/object inventory; PostgreSQL version/host and downtime choice; OIDC issuer and authorized legacy owner-proof process; actual members/brand assignments/reviewer; canonical snapshot hashing and validator contract; token KMS; provider dedupe/callback/cost finality; verified live historical outcomes; approved retention and restore evidence. Positive budget and publication permission are distinct external gates. Resolve these without weakening isolation, approval or preservation requirements.
