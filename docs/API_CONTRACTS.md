# Content OS v6 API and event contracts — M0 planned target

**Status: design artifacts, not implemented endpoints.** These files define the proposed v6 boundary for M1–M6. They neither modify the FastAPI runtime nor certify a provider, publication, tenant boundary, or milestone acceptance gate. The authoritative product target is [`spec/CONTENT_OS_ASTRA_BUILD_SPEC_v6.md`](spec/CONTENT_OS_ASTRA_BUILD_SPEC_v6.md), read in full (sections 1–24). The namespace `/api/v6` is a **proposal**, not a deployed server or compatibility alias.

## Files and reproducibility

| File | Purpose |
|---|---|
| [`contracts/build_contracts.py`](contracts/build_contracts.py) | Single deterministic source for schemas, endpoint policy metadata, events, lifecycle and coverage. Stdlib only; no application imports, network, database or provider calls. |
| [`contracts/target-v6.openapi.json`](contracts/target-v6.openapi.json) | OpenAPI **3.1.0**, JSON Schema 2020-12; typed requests/responses and all section 16 groups. Every operation is marked `x-implementation-status: planned`. |
| [`contracts/target-v6.events.schema.json`](contracts/target-v6.events.schema.json) | Standalone JSON Schema 2020-12 with local `$defs`; discriminated event union, mandatory envelope and mandatory type-specific payloads. |
| [`contracts/target-v6.lifecycle.json`](contracts/target-v6.lifecycle.json) | Exact section 13 job transitions; proposed publication graph; reservation transitions, guards and delivery semantics. |
| [`contracts/target-v6.coverage.json`](contracts/target-v6.coverage.json) | Machine-readable operation/group/milestone matrix, request/response names, status codes, concurrency/idempotency flags and deferred details. |
| [`contracts/test_contracts.py`](contracts/test_contracts.py) | Offline unittest reference/policy/schema-fixture tests; independent Draft 2020-12 checks with `jsonschema` and complete OpenAPI 3.1 validation with `openapi-spec-validator` when installed. |

From repository root:

```sh
.venv/bin/python docs/contracts/build_contracts.py
.venv/bin/python docs/contracts/build_contracts.py --check
.venv/bin/python -m unittest discover -s docs/contracts -p 'test_*.py' -v
# Also supported:
.venv/bin/python docs/contracts/test_contracts.py
```

Keep the generated JSON files in the same review/commit as generator changes. `--check` and the regeneration test fail on artifact drift. Do not hand-edit JSON. No timestamp, local path, provider result or runtime inspection is injected into generation. The recorded tests below do not create a deployment or call any endpoint.

## Legacy compatibility: what was actually inspected

Inspection baseline: commit **`d3e3f9934681dcb29e65194f9699566165ccd813`**, branch **`engineering/v6-m0-foundation`**. This is an actual commit ID obtained with `git rev-parse HEAD`, not a tree ID. This inspection is not the repository-wide CURRENT_STATE inventory; the parent M0 work owns that evidence.

Read `backend/main.py`, the full `backend/schemas.py`, all router modules (`assets`, `avatars`, `brands`, `health`, `personas`, `sources`, `videos`, `workspaces`) and `backend/services/auth.py`. Observed router declarations:

| Existing route family | Current declared behavior and incompatibility |
|---|---|
| `/health`, `/v1/health`; `POST /v1/jobs/tick` | Health/config summary and in-process scheduler tick; not a durable-job API. |
| `POST /v1/workspaces`; `GET /v1/workspaces/me` | Workspace creation without a verified user session; caller/default owner email; raw workspace key returned once. No v6 onboarding/membership authority can be inferred from this. |
| `/v1/brands`, `/v1/personas`, `/v1/avatars` | Create/list/read with workspace-key scope; no current user identity or explicit brand grants in the inspected dependency. |
| `/v1/sources`, `/v1/sources/{source_id}/evidence`, `/v1/evidence/search` | Research-source CRUD/evidence search; not upload quarantine/finalize, immutable source snapshots or transcript versioning. Lists are not the target cursor envelope. |
| `/v1/assets` | `MediaAsset` library records, optional placeholder object creation, arbitrary `extra`; **not** universal output assets or immutable content versions. |
| `/v1/videos` and video-specific `script`, `approve-script`, `resolve-broll`, `assemble`, `approve`, `publish`, `clips`, `jobs` | Video-centric synchronous response models; no target universal package/plan/publication-intent contract. The inspected script route passes `body.script`, not the optional `scenes` payload, to `edit_script`. |

Legacy authentication is `X-API-Key` resolved directly to a workspace. Legacy schemas use string IDs, float `spend_usd`/`spend_limit_usd` and second-based clip offsets; errors are ordinary FastAPI `detail` shapes. Target UUIDs, integer micro-currency, millisecond timing, structured errors, sessions, version approvals, ETags and idempotency are **not backported by this document**.

No legacy endpoint was removed, renamed, aliased or made to advertise the target contract. Do not replace runtime `/openapi.json` with this file. Migration must preserve original media and video records, link them additively to new asset versions, and label simulated publication history as simulated. The spec reports simulated providers; this contract task did not execute adapters or certify live provider behavior. Legacy keys cannot be promoted into individual identity or bypass new grants.

## API conventions

### Authentication and authorization

- `SessionCookie`: OIDC-derived, server-managed `__Host-contentos-session`, Secure/HttpOnly/SameSite with expiration and rotation. Mutations require both the cookie **and** `X-CSRF-Token`; implementation also validates Origin. OIDC login/callback details remain provider-selected M1 work.
- `ScopedCredential`: a separate revocable bearer credential restricted by actor, workspace, brand and operation scopes. It is not the legacy workspace key and cannot confer authority beyond the bound actor's roles. Session-only operations do not accept it.
- Explicit anonymous exceptions: `startLogin`, `completeLogin`, `initiateOnboarding`, `completeSocialOAuth`. Initiation is controlled/rate-limited; callbacks validate state and verified provider flow. Pilot onboarding codes do not enable public SaaS signup. `createWorkspace` still requires verified identity and a valid onboarding challenge.
- Global identity is not tenant access. Check active membership and explicit brand grants for every non-owner, including admin. Combined roles are allowed. Every referenced source, version, job, connection and publication must belong to the same authorized workspace/brand.
- `x-permissions` is normative policy metadata, **not evidence of an authorization implementation**. Owner/admin/editor can edit and generate; owner/admin/reviewer can approve; owner/admin/publisher can schedule approved work. Publisher social connection actions additionally require `can_connect_social`. Only owner may transfer ownership/delete a workspace. Operator reconciliation requires a separate operator entitlement **and** owner/admin tenant authority.
- A brand-scoped list is filtered to granted brands, never broadened by omission of `brand_id`. Workspace-wide audit similarly filters non-owner brand rows. Notifications belong only to their recipient and still-authorized resource scope. An inaccessible object is 404; a prohibited action on a known accessible object is 403.
- Execution records are workspace-owned (W) with explicit `scope_type`, `purpose`, `job_type` (DB `job_kind`) and `originating_operation_id`. Only `scope_type: WORKSPACE`, `purpose: ADMIN`, `WORKSPACE_EXPORT/requestWorkspaceExport` or `WORKSPACE_DELETE/requestWorkspaceDeletion` permit **both** `brand_id: null` and `campaign_id: null`. Brand jobs require a real granted brand; no synthetic brand or null-based all-brand access. Job steps/attempts and job events carry matching context; W/same-job composite FKs and null-safe scope checks remain required database work.
- Job retry/cancel uses **originating-operation authority, without an additional EDIT intersection**. Viewers can retry/cancel their permitted asset exports; publishers can retry/cancel permitted publication work. Current grants, credential restrictions and safe-retry state/caps still apply. Workspace export/delete remains owner-only; operator reconciliation still requires owner/admin plus separate operator entitlement. `roles_any_of` on retry/cancel is the eligible role envelope, not a grant independent of origin.
- Workers and callback handlers recheck tombstone, current actor authority, rights/consent, exact approvals and caps immediately before paid or publishing side effects. A worker identity is not blanket user authorization.

### Responses, pagination, concurrency and errors

- IDs are UUIDs. Snapshots are immutable. Current pointers and workflow state are mutable aggregates with integer revisions. Timestamps are UTC RFC3339 values ending in `Z`; requested publication local time is stored separately with an IANA zone.
- Closed request/snapshot objects reject unknown fields. Where a field is nullable it remains explicitly required unless otherwise stated; `null` is different from an omitted field. Separate schemas are used for requests, identity/current state, immutable versions, content variants, steps/attempts and event payloads.
- Collection reads use `cursor`/`limit`, default **25**, maximum **100**; responses contain typed `items`, nullable `next_cursor`, and `has_more`. Cursors bind tenant, filters and stable `(created_at, id)` ordering. Apply equivalent stable keys where the resource does not expose `created_at`; the actual opaque cursor encoding is an M1 choice.
- Long-running ingestion, production, rendering, preview, export, scheduling, cancellation, connection validation and deletion operations return **202** with `job_id`, `status_url`, `correlation_id`, `Location` and `Retry-After`. The `Location`/`status_url` point to the authorized job read route. Completion resources are discovered through `Job.result_resource_urls` and exact `result_version_ids`, never a fabricated success URL. A scheduled job acknowledgement is not external dispatch or publication.
- Optimistic operations require a strong quoted `If-Match` ETag, with no wildcard. ETag names the owning aggregate/current pointer even when the path includes an immutable version. Existing-target creation of a new version does not waive the precondition. Missing header is **428 PRECONDITION_REQUIRED**; stale mismatch is **409 STALE_VERSION** (deliberately the spec's 409, not a silent 412 variant). Reload/merge, never last-write-wins.
- Every billable or publishing mutation requires `Idempotency-Key`; many other mutations require it conservatively too. Scope: workspace + actor + operation. Hash normalized request including resolved exact inputs and relevant preconditions. Same key/hash replays the original response; same key/different hash is **409 IDEMPOTENCY_CONFLICT**, with no new work or spend. A request replay must be recognized before stale current-state preconditions can create a second logical operation. Ordinary replay cache default is seven days; billable/publication operation identity remains through applicable ledger retention. Provider billing deduplication is separate and must be verified.
- Error envelope always contains `code`, `message`, typed `field_errors`, `retryable`, `correlation_id`. Every operation declares 401, 403, 404, 409, 422, 429, plus 500/503; optimistic operations also declare 428. Error fields refer to request paths without echoing secrets. Missing idempotency uses **422 IDEMPOTENCY_KEY_REQUIRED**. Validation/body errors must be mapped into this envelope rather than leaking legacy FastAPI `detail` responses.
- Budget blocks consistently use **422 BUDGET_EXCEEDED**, `retryable: false` until an authorized budget change. Zero live cap is a hard zero. `429` includes `Retry-After`; retryability never authorizes blind provider resubmission.

## Section 16 coverage and milestone boundaries

The machine-readable coverage file lists every concrete operation. Milestones indicate **earliest intended implementation**, not completion.

| Required group | Planned operations | Milestone |
|---|---|---|
| Identity | Session/login/logout/current user; workspace switch; controlled onboarding/create/list/read; invitation create/list/accept/revoke; membership edit/revoke; explicit grants; owner transfer | M1 |
| Brands | Create/read/update/list; immutable profile versions; async voice preview, sample read and exact sample approval/rejection | M1–M2 |
| Sources | Private resumable multipart intent/part URL/status/cancel; source finalize; URL/text source; read/list/version; async process/cancel; transcript versions and alignment | M1–M3 |
| Packages | Campaign create/read/list; package manual create or async drafting; read/list/version; version review and approval/rejection; dependencies, claims/evidence and atoms reads | M2 |
| Plans | Async proposal; edited immutable versions; async estimate/read; exact plan approval/rejection; execution of exact approved package/plan/estimate | M2 |
| Assets | Universal list/read/version; selected-component regeneration; review and exact approval/rejection; rendition request/read; async private export/download access; review tasks/comments | M2–M3 |
| Video | Scene and timeline versions/read/list; script checkpoint; async preview/candidates; exact clip-selection versions, bounds/crop revisions and approval/rejection | M3–M4 |
| Jobs | Durable jobs/read/list; steps and provider attempts; safe retry; cancellation; operator reconciliation | M1 |
| Connections | OAuth start/callback; connection read/list/capability/profile; async validation; disconnect | M5 |
| Publications | Intent create/read/list; immutable revision/read/list; exact revision approval/rejection; schedule/pause/cancel/status/attempts; authorized async takedown | M5 |
| Analytics | Native metric query; deduplicated conversion ingestion/read; provider/customer usage and reservations | M1 usage; M6 metrics |
| Administration | Budgets/entitlements; owner export/delete/status; scoped audit; recipient notifications/read acknowledgement | M1 settings/audit; M6 lifecycle |

All six destination enum values represent the five social destinations with YouTube long-form/Shorts separated: `YOUTUBE_LONG`, `YOUTUBE_SHORTS`, `LINKEDIN_TEXT`, `INSTAGRAM_REELS`, `FACEBOOK_PAGE_REELS`, `TIKTOK_VIDEO`. Facebook personal publishing and newsletter sending are not silently included.

## Typed core and exact approval semantics

### Packages, plans and assets

`PackageVersion` contains the canonical section 8.3 fields: schema version, package/version/workspace/brand/campaign identity, thesis, business objective, audience, funnel stage, nullable offer, structured CTA, master narrative, exact brand profile version, source/claim/atom references and creator. Jurisdiction context is additional typed policy input. No filler evidence IDs are required for opinion-only content. Factual/quotation `SUPPORTED` claims require evidence IDs or explicit reviewer evidence structurally; retrievability and substantive review remain service checks.

`PlanVersion` binds the exact package, executable `PlanItem`s, selected outputs/destinations, immutable recipe/dependency bindings, rationale, structured output constraints, estimates and approved ceiling. Dependencies must be acyclic. Cost categories are exclusive; micro-currency values must share currency, high >= low, and reserve atomically across all applicable caps. `ExecutePlan` carries package/plan approval decisions and estimate identity; neither approval enables unlimited retries or undescribed work.

`AssetVersion.content` is a discriminated union of `WrittenContent`, `ScriptContent`, `VideoContent`, `CaptionContent` and `ImageContent`. Asset type is constrained to the matching variant. Written formats have blocks/claims/locks and separate newsletter subject/preheader; video binds source/script/timeline instead of a generic `dict`. `Asset` separates production, approval, rights and freshness. Running old jobs may finish old snapshots; those results do not inherit newer approval.

### Capped preproduction authorization — separate from production approval

Paid preparation cannot require a plan that does not yet exist. `POST /workspaces/{workspace_id}/preproduction-authorizations` accepts `PreproductionAuthorizationCreate` and returns **201 `PreproductionAuthorization`**. Only an authenticated owner/admin under current budget policy and a current brand grant (for non-owner) may create it. `GET /workspaces/{workspace_id}/preproduction-authorizations/{preproduction_authorization_id}` reads the immutable record; there is no cap/input update endpoint.

The request pins required brand, intended `actor_user_id`, nullable campaign/job, one `logical_operation_id`, allowlisted `operation_id` (DB `originating_operation_id`), exact `inputs` version/hash bindings, typed `operation_input`, `operation_if_match` when required, `input_sha256`, nonnegative `cap` with currency, expiry and reason. Server stamps workspace, authorization ID, approving actor/time and budget-policy revision. The actor must have permission for the originating operation. Database membership IDs are resolved from the verified user, never accepted as an invented identity.

| Paid pre-plan operation | Required request | Authorized work |
|---|---|---|
| `previewBrandVoice` | `VoicePreviewRequest` | Brand sample paragraph/script |
| `createSourceFromURL` | `SourceURLCreate` | Bounded research/retrieval |
| `processSource`, `alignTranscript` | `SourceProcess`, `AlignmentRequest` | Declared extraction/transcription/probe/alignment work |
| `draftPackage` | `PackageDraftRequest` | Package drafting, with research only when explicitly requested |
| `proposePlan` | `PlanProposal` | Plan proposal, not execution |

Each request requires `preproduction_authorization_id` and the same logical operation; every billable PREPRODUCTION job/step/attempt retains that ID. `operation_input` is the closed typed consuming request before its authorization ID is issued (DB `canonical_request`), not an opaque object. SHA-256 binds normalized operation, workspace/brand, actor, campaign, logical operation, exact versions/hashes, input body and applicable precondition, excluding the authorization ID to avoid a hash cycle. Server recomputes and rejects mismatches; no `latest` or undeclared paid substeps. Relevant `If-Match` is frozen as `operation_if_match` for process/alignment.

**Default live allowance is zero.** Atomic reservation checks configured workspace/job/campaign caps where applicable **and** the immutable authorization cap; bounded research and repair retries share that cumulative cap. Before job allocation, `job_id` may be null. First redemption atomically records a one-job binding and an explicitly authorized job cap; it cannot authorize a different job. An existing job binding must match. New input/actor/operation/cap requires a new authorization. Expiry/revocation is rechecked before dispatch; revocation history is append-only, not a mutation of the cap or prior spend. Authorization does not confer editorial approval on generated results.

PRODUCTION remains a separate branch requiring the exact approved package/plan, decision and selected inputs. Rendition, preview, clip-candidate and regeneration requests explicitly carry `approved_plan_version_id` and `plan_approval_decision_id`; preproduction authorization cannot fund them. ADMIN/PUBLICATION jobs instead bind their exact operation/actor/inputs through immutable `work_authorization_id` with configured caps; purpose alone is never paid authority, and no fake plan is created. Publications additionally require editorial/media/publication approvals and publisher authority. Pure unpaid local operations cannot dispatch billable work.

### Approval subjects

Every decision request requires a typed subject with `subject_type`, `subject_id`, **`subject_version_id`**, decision (`APPROVED` or `REJECTED`) and reason. The authenticated actor and immutable history timestamps are server-generated. Request subject IDs must equal the path and actual resource version; mismatches fail, never resolve `latest`.

| Subject type | Subject identity | Exact version |
|---|---|---|
| `PACKAGE` | package_id | version_id |
| `PLAN` | plan_id | plan_version_id |
| `ASSET` | asset_id | asset_version_id |
| `SCRIPT` | script asset_id | script asset_version_id |
| `PUBLICATION` | publication_id | publication_revision_id |
| `VOICE_SAMPLE` | sample_id | sample_version_id |
| `CLIP_SELECTION` | selection_id | selection_version_id |
| `RENDITION` | rendition_id | rendition_id (the rendition is immutable); required `scope: final_media` |

`SCRIPT` remains the universal asset type `SCRIPT`. Its `script_versions` row is an immutable **detail extension** of `asset_versions`, sharing its ID, not a second version-registry subtype. `VersionBinding.kind` is `ASSET` for scripts; SCRIPT approval targets `asset_version_id`, resolving to DB **asset/narration**. Registry kind `script` is not permitted. `VoiceSampleVersion` and `ClipSelectionVersion` have independent registry kinds/tables `voice_sample/voice_sample_versions` and `clip_selection/clip_selection_versions`, with `brand_voice` and `clip_selection` review scopes. `VoiceSample.approval_status` is a mutable projection, excluded from the immutable voice sample snapshot.

`POST /workspaces/{workspace_id}/renditions/{rendition_id}/decisions` approves/rejects the exact **rendition/final_media** subject under REVIEW authority and If-Match. Both subject IDs must equal the path rendition ID. Technical validation is separate from human approval. A publication using any rendition requires a matching `rendition_approval_decision_id`; final asset approval is not a substitute. No rendition means that field is explicitly null (e.g. LinkedIn text).

Package, plan, pre-avatar script, final asset and publication approvals are distinct checkpoints. Clip-selection/voice decisions add explicit review. A batch UI writes separate backend decisions. Review tasks represent pending work; `ApprovalDecision` is immutable history. Invalidation creates a new event/projection, not a rewrite of the original decision. Publication approvers use review authority; scheduling requires publisher authority, allowing one person only when separately granted both roles.

### Timeline, clips and publication intent

`TimelineVersion` follows section 12.2: integer milliseconds, rational FPS, canvas, typed tracks/shots/source ranges, fit/focal point/audio gain, caption and brand-template versions, plus render preset identity. **`TimelineWrite` takes `base_asset_version_id`, never output `asset_version_id`.** Under the aggregate If-Match, the server atomically creates a fresh timeline, fresh output asset version pinning that timeline, immutable `video_asset_bindings` row, pointer update and invalidations. Failure rolls back the entire transaction. `TimelineVersion.asset_version_id` is the returned fresh output binding, different from the base, **excluded from timeline content/dependency hash and prerequisite edges**. Output asset depends on timeline; the timeline depends only on base/actual input versions, never its output. Fresh-ID equality, correct path ownership and transaction atomicity require service/database checks, not merely JSON Schema. Actual media duration, not narration estimates, controls bounds. `SceneWrite.base_scene_version_id` identifies an existing scene for revision; null begins a new scene. Scene locks and selected component IDs prevent unrelated regeneration.

Clips bind an approved final-cut asset version, approved package and aligned transcript; they are not derived solely from an unreviewed transcript. Each selected moment has candidate/source bounds, crop, destination-profile version and separate destination set. Fewer than three moments requires explicit acceptance and reason; the schema permits one or two only with that acceptance, and never fabricates missing moments.

`PublicationIntent` pins asset/rendition, destination connection/profile, full metadata/visibility, schedule revision, requested local time/IANA zone/resolved UTC, tracking tags, asset approval and separate publication approval. New intent uses a unique logical publication ID; intentional reposting is a new explicit intent. Video requires a rendition; LinkedIn text may use null. Revision preserves logical identity and invalidates prior schedule approval. Validate all three time fields; ambiguous/nonexistent local times return typed errors rather than silently selecting an offset.

Dispatch rechecks exact approval, freshness, current membership/grants, account scopes, rights, avatar/voice consent, media validity and caps. More than 15 minutes late means pause + notification. `PUBLISHED` requires verified destination state/visibility and live verification timestamp, not merely a returned remote ID. Cancellation of uncertain remote work is reconciliation, not proof it never published. Takedown is an authorized request, not a deletion promise.

### Jobs and events

`Job` and `JobStep` include pinned version inputs, logical operation identity, durable state, result references, costs and errors; steps include input hash, attempt count, next attempt time, lease/heartbeat/fencing and provider request identity. `ProviderAttempt` separates accepted/not accepted/unknown from final outcome. `DEVELOPMENT_SIMULATED` cannot silently settle as `LIVE` spend. Operator resolution records established outcome and evidence; unknown retains reconciliation/reservation.

`UsageEntry` discriminates on `ledger`. `PROVIDER_COST` uses `ProviderCostUsageEntry.amount: SignedMoney` (signed integer currency micros, explicit currency) plus provider units. `CUSTOMER_CREDITS` uses `CustomerCreditsUsageEntry.credits` (signed integer), **without `amount` or a currency field**; DB storage has unit `credits` and currency NULL. Zero/negative adjustments are representable in the correct units. Cross-dimension fields, fabricated credit currency and fractional credits are rejected. Usage event mirrors reuse the identical discriminated union. `usage.preproduction_authorized` carries the immutable authorization; job events mirror explicit scope/purpose/operation/authorization bindings.

Every domain event requires `event_id`, `schema_version: 1`, literal `type`, UTC `occurred_at`, `workspace_id`, `aggregate_id`, positive `aggregate_version`, `correlation_id`, and a closed typed `data` payload. Event families: source, package, plan, asset, job, review, publication, metrics, usage, connection. A payload from a different family or an empty `{}` is rejected. Job/publication state-change schemas additionally enforce allowed from/to pairs; published transitions require verification fields.

Delivery is at-least-once via transactional outbox/inbox, with consumer/event deduplication. Aggregate version is not global order: gap/late events require version-aware fetch/reconciliation, not state regression. Verify envelope tenant and every referenced local/provider attempt. Outbound webhooks are disabled by default; if enabled, HMAC/timestamp/event ID and a five-minute tolerance are required, with exact signature canonicalization frozen before enabling. **Inbound callbacks use each provider's actual verification mechanism**; no fictitious universal HMAC endpoint is defined. Provider payloads cannot supply tenant authority or operational instructions.

## Validation evidence and remaining implementation work

The offline suite checks deterministic generation; no dangling local refs/discriminator mappings; unique operation IDs and matching path parameters; all required groups/operations; auth/CSRF exceptions; ETag/idempotency policy; required error envelopes; cursor bounds; closed typed core structures; exact approval subjects; positive and negative representative payloads; all job/publication state pairs; required event fields and payload discrimination. Optional `jsonschema` adds Draft 2020-12 schema validation and independent fixture validation.

**Latest M0 contract-repair run:** using `/agent/workspace/content-os/.venv/bin/python`, deterministic regeneration succeeded; `-m unittest discover -s /agent/workspace/content-os/docs/contracts -p 'test_*.py' -v` passed **42 tests, zero skipped**; `build_contracts.py --check` passed. Both installed independent validators ran: `jsonschema` (Draft 2020-12 definitions and positive/negative fixtures) and `openapi-spec-validator` (complete OpenAPI 3.1 document). Generated artifacts contain **128 paths, 154 operations, 241 schemas, 23 event types**. The suite includes 14 cross-contract regression tests covering shared script identity, voice/selection registry targets, rendition approvals, typed immutable preproduction authorization and input/precondition binding, required preplan authorization IDs, retained production approvals, timeline input/output separation, workspace scope and origin-derived retry/cancel, signed cost/credits, and event mirrors. This supersedes the earlier 25-test baseline with skipped optional validators.

This is **M0 design/schema/policy validation only**, not runtime implementation or milestone acceptance. No runtime route, PostgreSQL locking/isolation/migration, worker restart, media decoding, OAuth account, provider spend, real publication or UI acceptance test was run by this task. Cross-field identity/hash comparisons, one-job redemption, FK/scope enforcement, atomic creation/reservation and live authority checks remain implementation gates.

Important boundaries still requiring implementation/design review:

1. OIDC provider selection, credential provisioning/rotation, exact login failure callbacks, storage-provider multipart details and cookie deployment settings need M1 ADRs. Callback code/state here describes the success path; provider-denial variants are explicitly not final.
2. JSON Schema cannot enforce tenant foreign keys, authorization, immutable persistence, path/body ID equality, valid ETag lookup, normalized replay storage, evidence retrievability, acyclic dependency graphs, source-time cross-field bounds, unique timeline IDs, sum/currency constraints, DST resolution, remote status verification or correct lease fencing. Those are normative service/database checks, not passing schema-test claims.
3. Additional claim/evidence authoring/reclassification, recipe/persona library, review diff/restore and consent/media/avatar administration routes must be frozen before their milestone UI. Typed snapshots/refs exist; this is not a claim that every section 8 table has full CRUD. Public signup/subscription/billing is M7/R2 and needs separate commercial specification.
4. Provider-specific inbound callback schemas/routes, OAuth denial variants, platform payloads, scope/app approval evidence, current destination profiles and deletion capabilities remain M4/M5 adapter work. The publication transition graph is explicitly proposed; section 13 job transitions are copied exactly. No provider access failure counts as a release pass.
5. Auditable deletion, owner reauthentication, signed URL expiry, storage purge/backup/provider exceptions, retention, notification delivery and privacy filtering require M6 implementation and evidence. Archived or simulated historical records cannot be turned into live publication evidence by migration.
6. The stdlib validator intentionally implements only the emitted keyword subset; it is not a general OpenAPI meta-schema validator. The latest run also used the installed independent JSON Schema and OpenAPI validators; keep them available in contract CI so those tests are not skipped. Do not describe any of these tests as full runtime conformance.

These boundaries preserve the full R1 requirements; they are not scope cuts. Target contracts must be wired to schemas/API/workers/UI together with corresponding milestone acceptance evidence before any planned operation is called implemented.

### Final alignment review
Manual assets (including SCRIPT) may have plan_version_id null; paid production and regeneration still require an approved plan. Clip candidate requests, candidate responses and selection versions pin final_cut_rendition_id as well as the asset version, package and transcript. Validate that rendition belongs to the selected final cut and has exact final-media approval. Two additional regression tests cover these invariants. Install the pinned jsonschema validator before running the complete 42-test suite; the generator itself remains standard-library-only.
