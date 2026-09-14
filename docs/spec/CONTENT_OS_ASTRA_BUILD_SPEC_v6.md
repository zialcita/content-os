# AI Marketing Box — Content OS
## Engineering Build Specification for Astra

**Version:** 6.0  
**Date:** September 11, 2026  
**Product owner:** Martin Zialcita, AI Marketing Box  
**Initial customer teams:** AI Marketing Box and Tailor Law  
**Implementation repository:** https://github.com/zialcita/content-os  
**Status:** Engineering handoff draft. Confirmed product decisions are binding; engineering defaults below are proposed implementation defaults. No production deployment, expenditure, or external publication is authorized by this document alone.

---

## 1. Purpose and authority

Build a multi-tenant content production application that turns a topic, document, human recording, or approved avatar script into a reviewed campaign of videos and written content, with an integrated publishing calendar and direct social connections.

This document is a standalone build contract. It replaces the earlier YouTube-only scope for this project when adopted into the repository. Preserve the earlier specification and MVP contract as historical documents; update root documentation to point to this contract. Do not allow an older instruction excluding scheduling or multi-platform publishing to silently reduce this scope.

The clean specification does not require a destructive rewrite. Inspect and reuse sound code in the existing repository, introduce additive migrations, and preserve existing records. Do not claim completion from simulated responses, placeholder URLs, screenshots of an empty interface, or a passing mock-only pipeline.

Normative terms:

- **MUST:** Required for the milestone or release in which the feature appears.
- **SHOULD:** Default implementation unless an architecture decision explains a better equivalent.
- **MAY:** Optional; cannot delay required work.
- **Confirmed:** Explicitly requested by Martin in this conversation.
- **Default:** A concrete proposed value that can be configured or revised; not an asserted user approval.
- **External gate:** A provider, account, credential, commercial, or operational dependency that implementation alone cannot satisfy.

If external access blocks one integration, continue independent work, show the integration as blocked, and retain its release requirement. Do not redefine a blocked requirement as completed.

## 2. Product decisions and release boundaries

### 2.1 Confirmed decisions

| ID | Decision |
|---|---|
| PD-01 | AI Marketing Box and Tailor Law teams are the first users. |
| PD-02 | Clients need their own self-service environment; public subscription SaaS follows successful use. |
| PD-03 | A selected campaign includes a main video, 3–5 clip moments adapted for YouTube Shorts, Instagram Reels, Facebook Reels and TikTok, plus a LinkedIn post, article and newsletter. |
| PD-04 | Scheduling and social publishing happen inside the application, with downloads also available. |
| PD-05 | Initial editing includes scenes, captions, trims, reframing and media replacement. A sophisticated timeline editor is deferred. |
| PD-06 | Astra is the intended engineering execution agent. |
| PD-07 | Both human-upload and avatar-led routes are supported; video is optional for text-only campaigns. |

### 2.2 Product defaults

Each client receives a private workspace in one maintained application, not a separately forked installation. A person can belong to multiple workspaces and switch between them. Client users can operate the campaign workflow themselves within their entitlements; self-service does not mean that public signup or payment collection is required during the pilot.

Start with two separate workspaces: AI Marketing Box and Tailor Law. Create them through an authorized onboarding flow; do not invent users, send invitations, or connect accounts without appropriate user actions. Names are seed labels, not embedded authorization rules.

Tailor Law's default publication policy requires a designated human reviewer. No legal, medical or financial compliance certification is offered. Other workspaces also require final approval in Release 1; automated publishing means dispatching approved scheduled material, not bypassing review.

One “clip moment” is an editorial selection, not a single distribution file. Five moments across four channels yield up to 20 rendition/publication combinations. Reuse a render when its content and technical settings are identical; preserve separate platform metadata and publication records.

### 2.3 Release definitions

| Release | Required outcome | Explicit exclusions |
|---|---|---|
| Development milestones | Secure application, source processing, text/video generation, review, exports and integrations delivered incrementally | Must not be described as the complete product |
| R1 — Team/client pilot | Two isolated teams; invited users; both video routes; required written assets; 3–5 moments; five direct social destinations; calendar; downloads; basic metrics and usage | Public checkout, public signup, automatic strategy changes, advanced timeline editing |
| R2 — Subscriber SaaS | Self-service signup/onboarding, subscriptions, entitlements, invoices/payment lifecycle, account recovery, customer support and abuse controls | Enterprise SSO/data residency unless separately scoped |
| R3 — Expansion | Advanced editing, more formats/providers, multilingual production, recommendation learning and guarded autonomous creation | Not a prerequisite for R1 |

R1 social destinations are YouTube long-form and Shorts, LinkedIn text posts, Instagram Reels, Facebook Page Reels and TikTok video. Account types and permissions must be verified in discovery. Personal Facebook profile publishing is not implicitly included. If a desired account is unsupported, surface the limitation to Martin; do not substitute another account silently.

## 3. Repository starting point and preservation

Earlier read-only inspection of the default branch found a FastAPI/SQLAlchemy backend, Next.js interface, workspace API keys, video scenes, render jobs and a basic cost ledger. Inspected HeyGen, Shotstack and YouTube adapters returned simulated results even with configuration present. The inspected scheduler used an in-process loop; schema initialization used create_all; the test file contained health, simulated pipeline and spending-limit tests. Those tests were read, not executed.

This is a provisional inventory, not a current deployment certification. At milestone M0 Astra MUST record the exact current commit SHA, branch, dependency versions, schema, configuration modes, tests and deployment evidence in CURRENT_STATE.md. Do not treat a Git tree SHA as a commit SHA. Reconcile differences before changing code.

Preserve usable interface elements, provider boundaries and domain data. Existing media_assets are media files, not replacements for the required universal assets model. Existing video_projects must link to new asset versions through migration. Existing simulated “published” records must remain clearly identified and must not appear as live publications.

The original workspace key may temporarily remain as a restricted legacy credential. It must not act as an individual user identity or bypass brand permissions. Existing users must be migrated safely to membership records; matching email strings alone is not sufficient proof of account ownership.

## 4. Architecture and engineering choices

Use a modular application with a web interface, API, dedicated workers, PostgreSQL and private object storage. Do not introduce microservices for each provider.

| Component | Proposed implementation default |
|---|---|
| Web | Existing Next.js application, TypeScript, responsive workflow UI |
| API | Existing FastAPI application, validated schemas and generated OpenAPI |
| Database | PostgreSQL with SQLAlchemy and Alembic migrations |
| Jobs | PostgreSQL-backed durable job/step records and separate Python worker processes |
| Locking | Transactional row claims, leases, heartbeats and fencing tokens; Redis optional for non-authoritative cache/rate limiting |
| Media | Private S3-compatible object storage; R2-compatible adapter |
| Authentication | Standards-based OIDC login with server-managed sessions; select maintained provider in M0 |
| AI | Task-based provider adapter; structured outputs; model/prompt versions recorded |
| Transcription | One verified provider with time-coded output behind an adapter |
| Avatar | HeyGen as the first real implementation |
| Assembly | Shotstack as first candidate, subject to M0 capability proof; FFmpeg for validation, proxies and supported local transformations |
| Publishing | Separate direct adapters for the five destinations; one publication owner per scheduled item |
| Observability | Structured logs, correlation IDs, job dashboard, errors and cost alerts |

Astra may choose an equivalent maintained implementation when justified by repository compatibility and required behavior. Record material choices in an ADR before implementing the affected module. A change to release scope, approval authority, data sharing, recurring commercial commitment or spending limits requires product-owner input. Routine libraries, internal function names and indexes do not.

Pin supported dependency versions and commit lockfiles. Production must use PostgreSQL; SQLite-only passing tests do not establish locking, migrations or tenant protection behavior. Provider credentials are server-side secrets; browser code must never receive them.

Deploy web/API and workers separately. No required job may depend on keeping an HTTP request or API process alive. Production scheduling uses persisted database intent, not browser timers.

## 5. Core user journeys

### 5.1 Onboard a workspace and brand

Owner creates a brand, enters audience, positioning, voice examples, logo/colors/fonts, prohibited terms, pronunciation, offers, CTAs and approval settings. System generates a sample paragraph and script using a configured provider. User reviews and saves a versioned brand profile. Invitees receive scoped roles through an authorized invite action.

### 5.2 Start from an idea

Select brand and campaign objective; enter topic, audience, offer and source evidence. Retrieve external evidence through a configured search/retrieval adapter when required. Display retrieved sources and claim statuses. Produce a draft package. User edits and approves the package, chooses the output plan, accepts the estimated production budget, then starts production.

A topic may produce written assets without creating any video. Do not require avatar configuration for text-only use.

### 5.3 Start from a human recording

Upload source through a resumable private transfer; validate/scan; extract media properties; transcribe; show transcript with speaker labels and source timestamps. User corrects transcript and confirms clip readiness. Build the same package structure used for idea-based content.

For finished videos, offer “preserve and derive,” “add captions,” or “edit.” Preserve-and-derive must not unnecessarily rebuild the entire source. Source video remains immutable.

### 5.4 Produce an avatar video

Use an approved package to write an editable script and scene plan. Validate avatar/voice authorization and pronunciation. User approves script and estimated render plan. Submit real avatar work, retrieve outputs, assemble with approved visual treatments and captions, and present a final review.

Changing an already approved narration creates a new script version and invalidates affected output approval. Exact model-generated narration must be reviewable before paid avatar rendering.

### 5.5 Review a campaign portfolio

Show all requested items with state, preview, estimated/actual usage, revision notes and blockers. User selects 3–5 distinct clip moments if the source supports that many. If fewer viable moments exist, explain the shortfall and ask the user to accept fewer or supply more source material; do not fabricate weak clips to meet a count.

Generate or reuse platform renditions, plus the LinkedIn post, article and newsletter. Users can revise individual assets, lock sections/scenes, retry failed items, and download successful items independently.

### 5.6 Schedule and publish

Connect accounts through OAuth; choose approved asset versions and metadata; choose a local date/time and timezone; preview the destination-specific publication; approve. Scheduler dispatches at the stored time after revalidation. Report upload/processing status separately from published/live status.

User can download at any point after an output is available, independent of connector access. Downloading does not mark an item published.

## 6. Scope of inputs and outputs

### 6.1 R1 inputs and defaults

| Input | R1 behavior | Default limits |
|---|---|---|
| Topic/pasted text/Markdown | Parse to draft package; research as required | 100,000 characters per pasted source |
| PDF | Extract text with page locators | 50 MB / 200 pages; scanned-only pages require a text alternative in R1 |
| DOCX | Extract paragraphs and tables with stable locators | 50 MB |
| Public article URL | Bounded public fetch, extract, preview and source snapshot | 10 MB fetched payload; no login bypass |
| MP4/MOV | Probe, normalize if needed, transcribe and derive | 2 GB / 60 minutes per source |
| MP3/WAV/M4A | Probe, transcribe and derive; avatar or visual assembly optional | 2 GB / 60 minutes |
| SRT/VTT | Import timestamped transcript; validate against associated media | 10 MB |
| YouTube link | Store reference; use permitted available text/media route | If unavailable, request transcript or authorized original file |

These are configurable product defaults, not provider promises. R1 must reject unsupported input with a recovery path. PPTX, image OCR, CSV and complex scanned documents are R3 additions unless reprioritized. No silent extraction that presents missing sections as complete.

Default production language is English. Accept Unicode names and punctuation and a pronunciation dictionary. Japanese and other languages require separate evaluation and are R3 by default.

### 6.2 R1 outputs

- Main video: uploaded source preserved or edited, or avatar production; default avatar target 3–10 minutes, maximum 10 minutes until capacity validation.
- Clip moments: selectable 3–5 per campaign; default 20–60 seconds with manual bounds. Platform validation may allow other durations.
- Renditions: 16:9 main and 9:16 short-form, up to 1080p; captioned and uncaptioned export; SRT/VTT; platform-specific metadata.
- LinkedIn post: editable text plus optional selected image; personal profile/company page capability separately validated.
- Article: editable structured text, default 800–1,500 words, source links and suggested internal links. Download as Markdown and sanitized HTML.
- Newsletter: editable subject, preheader, body and CTA; default 400–800 words. Download as text and sanitized HTML. Sending email is not R1.
- Publication package: media, captions, text/metadata and manifest in a downloadable archive. Archive creation is asynchronous and private.

Word counts are recipe defaults, not enforced padding. Main-video thumbnails may be supplied or produced from deterministic branded templates; an advanced thumbnail designer is not R1. The system must support selecting the thumbnail where the connector supports it.

## 7. Permissions and tenant boundaries

Users are global identities. Workspace memberships and brand grants determine access. One user's access to two workspaces does not permit cross-workspace source reuse without explicit export/import and ownership confirmation.

| Action | Owner | Admin | Editor | Reviewer | Publisher | Viewer |
|---|---|---|---|---|---|---|
| Manage membership/brand grants | Yes | Yes, excluding ownership transfer | No | No | No | No |
| Set budgets/provider credentials | Yes | Yes | No | No | No | No |
| Create/edit/generate within limits | Yes | Yes | Yes | No | No | No |
| Approve editorial content | Yes | Yes | No | Yes | No | No |
| Connect social accounts | Yes | Yes | No | No | Yes, when granted | No |
| Schedule/publish approved content | Yes | Yes | No | No | Yes | No |
| View/export permitted assets | Yes | Yes | Yes | Yes | Yes | Yes |
| Delete workspace/transfer ownership | Yes | No | No | No | No | No |

Roles can be combined; every non-owner membership requires explicit brand access. Admin operations must not allow an admin to grant themselves ownership. An owner can appoint one person to review and publish; the audit record must preserve the distinct actions.

Tenant checks apply to API reads/writes, workers, search, object URL issuance, exports and callbacks. Validate references belong to the same workspace and authorized brand. Worker service identity is not permission to run arbitrary user work. Recheck revoked permissions before paid or publishing side effects.

Use secure, HttpOnly, SameSite cookies, CSRF protection for state-changing browser requests, and session expiry. Scoped API credentials are separate from login sessions, rotatable and revocable. Invitations expire after seven days by default and are accepted only by the verified intended identity.

## 8. Domain contracts

### 8.1 Shared rules

IDs are UUIDs. Tenant-owned entities carry workspace_id and, when brand-owned, brand_id. All timestamps are UTC with timezone-aware storage. Money uses integer micro-units or fixed decimal, never binary floating point. Store currency explicitly. Version snapshots are immutable; current pointers are mutable with optimistic locking.

Tenant-consistent composite foreign keys or equivalent database constraints MUST prevent cross-tenant references. Add indexes for workspace/brand plus status/time. Define on-delete behavior in migrations; paid operations, approval history and publication lineage cannot disappear through accidental cascades.

### 8.2 Required entity groups

| Entities | Minimum contract |
|---|---|
| users, workspace_memberships, brand_grants | Verified identity, role set, lifecycle state and explicit access |
| workspaces, brands, brand_profile_versions | Owner, timezone, entitlements, voice/visual/policy snapshot |
| campaigns | Brand, objective, audience, offer, CTA, status; default “Standalone” campaign allowed |
| source_assets, source_versions | Original URI/hash/type/size, rights assertion, extraction state, source snapshot |
| transcript_versions, transcript_segments | Source media version, speaker label, start/end milliseconds, text, confidence when provided, alignment status |
| evidence_items, claims, claim_evidence_links | Source locator/quote/retrieval date, claim type and verification state |
| content_packages, content_package_versions | Narrative and strategy snapshot, source/claim references, persona/brand version |
| content_atoms | Package version, type, text, source/evidence links |
| asset_plans, asset_plan_versions, plan_items | Selected output, recipe version, dependency IDs, estimate, budget ceiling and approval |
| assets, asset_versions | Universal output identity, type, content snapshot, exact dependencies and editorial state |
| renditions | Asset version, delivery profile, object hash/URI, technical properties, validation |
| dependency_edges | Typed immutable-version relationships; acyclic |
| video_projects, scenes, shots, timeline_versions | Asset version, ordered scene text, source ranges, media references and timeline |
| media_assets, media_rights, consent_records | Provenance, permitted use, expiry/revocation, artifact |
| production_jobs, job_steps, provider_attempts | Execution states, input snapshot, leases, errors, provider request and costs |
| review_tasks, approval_decisions, comments | Subject/version/scope, actor, timestamp, comment anchor and resolution |
| social_connections, publications, publication_attempts | Brand/account scope, encrypted tokens, schedule, remote identity and outcome |
| budget_reservations, usage_ledger, entitlements | Atomic reserve/settle/release, provider and customer usage separated |
| metric_snapshots, conversion_events | Native definitions, measurement windows, deduplication and provenance |
| audit_logs, event_outbox, event_inbox, notifications | Mutation metadata, event delivery and user-action status |

Exact table consolidation is an engineering decision, but contracts cannot be omitted. Review tasks describe pending work; approval decisions are immutable history. Do not overload one mutable review row to represent both.

### 8.3 Canonical package snapshot

```json
{
  "schema_version": 1,
  "package_id": "uuid",
  "version_id": "uuid",
  "workspace_id": "uuid",
  "brand_id": "uuid",
  "campaign_id": "uuid",
  "title": "string",
  "primary_thesis": "string",
  "business_objective": "string",
  "target_audience": "string",
  "funnel_stage": "awareness|consideration|conversion|retention",
  "offer_id": null,
  "primary_cta": {"text": "string", "destination_url": null},
  "master_narrative": "string",
  "brand_profile_version_id": "uuid",
  "source_version_ids": [],
  "claim_ids": [],
  "atom_ids": [],
  "created_by": "uuid"
}
```

Offers and URL CTAs may be null for educational material. A source-free opinion package is allowed when clearly classified; invented evidence is not. Schema validation must require appropriate evidence for factual claims, not require meaningless placeholder IDs.

## 9. Versioning, approvals and dependencies

All jobs bind exact versions of source/transcript, package, plan, recipe, persona, script and timeline as applicable. Never dereference “latest” while producing an approved asset. Record model/provider/prompt versions and source hashes for reproducibility.

| Change | Required behavior |
|---|---|
| Package thesis, claim, narrative, offer or CTA | New package version; affected unpublished assets stale; related schedules paused |
| Transcript correction | New transcript version; invalidate affected derivatives; realign timing if needed |
| Asset-local wording | New asset version; other assets unchanged unless user promotes correction to package |
| Caption, scene narration, trim, crop or replaced media | New asset/timeline/rendition version; affected approval invalidated |
| Unrelated locked scene | Preserve content and existing usable render |
| Brand policy or consent revision | Revalidate affected pending publication; do not rewrite silently |
| Already live publication | Preserve history; create correction/takedown review item |
| Schedule/account/metadata change | New publication revision; reapproval before dispatch |

Default R1 review checkpoints: package and production plan; video script before avatar spending; final assets; publication schedule. A user can approve a batch in one screen, but the backend writes separate decisions for each version. Generation approval does not authorize external publication.

Use distinct fields for production status, approval status, rights status and freshness. An approved but stale output is not dispatchable. Running jobs may finish old versions; their result cannot inherit a newer approval.

Dependency graph must support a clip derived from a final cut and linked to the approved package. Clips cannot be generated solely from an unreviewed transcript. Do not regenerate successful unrelated assets when one dependency fails.

## 10. Ingestion, research and claim handling

Upload protocol: create upload intent → transfer into private quarantine → finalize and verify size/hash/type → scan/probe → approved private storage → branch into extraction/transcription → user review when needed → package drafting. Transfer completion is not scan clearance.

Support resumable multipart upload, bounded processing, invalid/corrupt file handling, encrypted-document rejection with instructions, and cancellation. Duplicate detection stays within permitted workspace/brand scope. Do not reveal matching files in another client workspace.

Public URL fetching MUST block local/private/reserved addresses, unsupported protocols and unsafe redirects, including after DNS resolution. Enforce payload, decompression and timeout limits. Do not fetch authenticated content through credential guessing or bypass protection. Source text and web pages are untrusted data and cannot grant permissions or issue operational instructions.

Research results retain URL, title, retrieval time, content snapshot or permitted excerpt, and locator. Claim classes: factual, quotation, opinion, personal anecdote. Verification states: unreviewed, supported, unsupported, contradicted, expired. “Supported” requires a retrievable source relationship or explicit reviewer evidence, not a model-supplied URL alone.

High-severity unsupported/contradicted claims block final approval until corrected or explicitly reclassified with a reviewer reason. A reviewer cannot mark fabricated evidence valid. Show relevant source excerpts alongside claims. Tailor Law content requires jurisdiction context in the brief and designated review of substantive legal assertions.

Preserve original spoken transcript. Text corrections must not imply the speaker said new words. Track segment IDs and media times separately from presentation text. When timing cannot be trusted after edits, block clip production until alignment is repaired or manually confirmed.

## 11. Planning and asset generation

An asset plan is an executable, versioned set of line items. Each item records asset type, destination set, recipe version, prerequisites, rationale, estimated range, and output constraints. Users can add/remove/defer before approval. Changing selected work creates a new plan estimate and approval.

Start with explainable recipe rules, not a prediction engine. Each written derivative uses the approved package plus source evidence and the format recipe. A LinkedIn post should communicate a professional insight; an article should develop the topic; a newsletter should serve a relationship and CTA. Do not simply truncate a transcript three ways.

Structured generation must validate output schema, required sections and claim references. Schema repair retries count toward job limits. Failed validation is not success. Store draft diffs and allow reject/restore. Manual edits and locked blocks survive unrelated regeneration.

## 12. Video and editing contract

### 12.1 Editorial controls

R1 editor MUST provide scene list/order, scene narration, media replacement, caption correction/style, clip in/out points, crop/reframe preview and brand template selection. Use browser previews and proxy files where appropriate. Full arbitrary multitrack editing, keyframe animation and complex compositing are deferred.

The UI must preview the selected source range and show the cost impact of re-rendering. If a provider cannot regenerate one scene independently, state that a full render is required before submitting it.

### 12.2 Timeline schema

Use integer milliseconds for editorial timing and an explicit frame-rate rational for export. Validate positive durations and source bounds. The assembly compiler resolves frame rounding consistently.

```json
{
  "schema_version": 1,
  "timeline_version_id": "uuid",
  "asset_version_id": "uuid",
  "duration_ms": 60000,
  "canvas": {"width": 1080, "height": 1920, "fps_num": 30, "fps_den": 1},
  "tracks": [{
    "id": "video-main", "kind": "video", "z_index": 0,
    "shots": [{
      "id": "uuid", "media_version_id": "uuid",
      "start_ms": 0, "duration_ms": 60000,
      "source_in_ms": 0,
      "fit": "cover", "focal_point": {"x": 0.5, "y": 0.5},
      "gain_db": 0
    }]
  }],
  "caption_track_version_id": "uuid",
  "brand_template_version_id": "uuid"
}
```

Actual returned media duration determines timing. Estimated narration duration is for planning only. Audio ducking, fades and loudness targets belong in a versioned render preset; use a default stereo loudness target of -16 LUFS and true peak at or below -1 dBTP unless a destination requires another setting. These are product export defaults requiring measured validation.

### 12.3 Media resolution and rights

Default visual order: brand-owned library → campaign uploads → approved licensed stock → deterministic brand graphic → user selection. AI-generated B-roll is an optional R3 provider path, not required for R1. R1 avatar assembly must still support genuine B-roll/media placement, captions and branding.

Every media item records source, license/consent, permitted uses, expiry and generation prompt when relevant. Do not present generated illustrations as authentic evidence footage. Avatar/voice consent is checked before rendering and again before publishing. Revocation blocks new usage; existing live content enters review.

### 12.4 Clip selection and platform adaptation

Rank candidates by self-contained meaning, hook/payoff, transcript clarity and visual continuity. Show source ranges and a short selection rationale. User selects moments and edits bounds before final rendering. A clip must not cut out qualifying language in a way that changes a claim's meaning.

Vertical framing must preserve speakers and essential screen text. Offer manual crop and letterbox alternatives. Safe zones, length limits, media formats and caption rules are versioned destination profiles verified against current provider documentation during implementation. Do not hard-code one universal limit as valid for every platform.

### 12.5 Media acceptance

Output file exists and decodes; duration/dimensions match approved settings; no unintended blank segments; audio is present when expected; caption intervals are valid; no clipped words at approved bounds; important text remains visible; approved names are pronounced correctly. Automated media validation and human editorial acceptance are both required.

## 13. Durable jobs and external side effects

Job states: QUEUED, RUNNING, WAITING_PROVIDER, WAITING_USER, RECONCILING, SUCCEEDED, FAILED_RETRYABLE, FAILED_PERMANENT, CANCEL_REQUESTED, CANCELLED. Each transition has an audit record and optimistic concurrency check.

| From | Allowed next state | Condition |
|---|---|---|
| QUEUED | RUNNING, CANCELLED | Worker atomically claims lease, or cancellation before dispatch |
| RUNNING | WAITING_PROVIDER, WAITING_USER, RECONCILING, SUCCEEDED, FAILED_RETRYABLE, FAILED_PERMANENT, CANCEL_REQUESTED | Persist step outcome |
| WAITING_PROVIDER | RUNNING, SUCCEEDED, RECONCILING, FAILED_RETRYABLE, FAILED_PERMANENT, CANCEL_REQUESTED | Verified callback or polling result |
| WAITING_USER | QUEUED, CANCELLED | Required user action completed or abandoned |
| FAILED_RETRYABLE | QUEUED, FAILED_PERMANENT, CANCELLED | Retry policy and remaining budget permit |
| RECONCILING | WAITING_PROVIDER, SUCCEEDED, FAILED_PERMANENT, CANCEL_REQUESTED | Provider outcome established; no blind resubmit |
| CANCEL_REQUESTED | CANCELLED, SUCCEEDED, RECONCILING | Record what actually happened remotely; block downstream work |

Each step stores input hash, logical operation ID, attempt count, next attempt time, lease owner/expiry, heartbeat, fencing token, provider request ID, output references, error class and estimated/actual cost. An expired worker cannot commit with an old fencing token.

Persist submission intent before making an external call. A timeout after possible acceptance enters RECONCILING. Resubmit only when the adapter can prove nonacceptance or supports a verified deduplication key. If status is unknowable, request operator resolution. Internal idempotency does not guarantee provider billing semantics.

Default retry policy: at most three total submission attempts for confirmed-safe retryable operations, exponential backoff with jitter, honor retry-after, and remain within the approved cost cap. Polling is separate from submission attempts. Timeout budgets are configurable per provider; stalled provider work must become visible, not remain indefinitely “running.”

Use transactional outbox events and deduplicated inbox delivery. Worker claims must be atomic, including when Redis is unavailable. Database restart recovery must not depend on a best-effort process lock.

Campaign aggregate states include DRAFT, IN_PRODUCTION, WAITING_USER, PARTIAL_SUCCESS, READY_FOR_REVIEW, READY_TO_SCHEDULE, COMPLETE, CANCELLED and FAILED. A failed render must not hide successful text assets.

## 14. Cost accounting and entitlements

Provider operations reserve funds atomically across workspace, campaign and job caps before dispatch. Use fixed precision. Simulated operations never settle as real provider spend. Actual provider cost and customer credits are separate ledgers.

Reservation lifecycle: RESERVED → SETTLED or RELEASED; adjustments are additional immutable entries. Remote uncertain outcomes retain an appropriate reservation until reconciliation. Cancellation may still incur provider cost and must not imply a refund.

No positive paid-production budget is invented for Martin. Default unconfigured live budget is zero: work can proceed with tests and explicitly labeled development fixtures, while real paid operations wait for an owner-entered budget and configured provider. Approved plan caps authorize only the described production, not unlimited retries or additional assets.

R1 defaults for sizing: 10 users/workspace, 5 brands/workspace, 100 GB stored/workspace, 2 concurrent paid jobs/workspace. Admin-configurable entitlements may override them. These are capacity planning values, not a priced subscription offer.

Estimate exclusive cost categories: language model, transcription, avatar, licensed/generated media, assembly, storage/egress, publishing/analytics and other variable services. Include units and price snapshot date. Do not double-count a category inside both campaign cost and an additional monthly term.

Show estimate range before production, actual known usage afterward, and unsettled usage separately. Reconcile ledger totals against provider records during real-provider gates. Warn at 80% of a configured cap, block beyond 100%; zero is a hard zero, not a falsy fallback to another budget.

## 15. Scheduler and social connectors

### 15.1 Connector contract

Every adapter MUST implement connection validation, capability discovery, asset validation, submit, status reconciliation, token refresh where supported, metrics retrieval where permitted, and delete/unpublish capability reporting. Unsupported operations return a typed capability error.

For each destination, maintain a capability matrix: account type, permissions/scopes, approved application status, supported content formats, media limits, upload flow, processing flow, scheduling behavior, metrics, revocation and deletion. Validate against current official documentation in M0 and real accounts before release. Do not infer permissions from a configured API key.

OAuth state must bind the initiating user, workspace and brand. Account connections store verified remote identity and encrypted tokens. A connection belongs to one brand unless explicit shared use is configured and authorized. Tokens and signed URLs are redacted from logs.

### 15.2 Publication intent

Each intent pins asset version, rendition, caption/title/description, destination account, schedule revision, timezone, approval decision, tracking tags and a unique logical publication ID. Unique constraint on that logical ID prevents accidental duplicate submission; intentional reposting requires a new explicit intent.

Store requested local time, IANA timezone and resolved UTC instant. Reject ambiguous/nonexistent daylight-saving local times with a correction prompt. Moving a scheduled item requires reapproval. Default late-dispatch policy: within 15 minutes dispatch if still valid; beyond 15 minutes pause and notify rather than surprising the user with old content.

Publication states: DRAFT, SCHEDULED, PAUSED, SUBMITTING, PROCESSING, PUBLISHED, RECONCILING, FAILED, CANCELLED, TAKEDOWN_REQUESTED, TAKEN_DOWN. Remote identity alone is insufficient for PUBLISHED; verify destination state and requested visibility.

Before dispatch recheck role/account permissions, exact approval, freshness, rights, consent, media validity and publication limits. Reconcile uncertain upload/publish outcomes before retrying. Platform scheduling may be used when verified; otherwise the application performs timed dispatch itself.

### 15.3 Completion criteria

R1 requires a verified controlled publication and metric retrieval where supported on each required destination, using authorized accounts. If a platform denies access or does not expose a desired metric, record the exact gate and supported alternative. Exports remain available, but an export cannot satisfy the direct-publishing gate. Never silently publish to a different channel.

## 16. API and event contracts

All endpoints require scoped authentication except login callbacks, controlled onboarding initiation and verified provider callbacks. Long-running operations return 202 with job_id and status_url. Reads paginate using cursor/limit, default 25/max 100.

| Group | Required endpoints/operations |
|---|---|
| Identity | Session/login/logout; current user; workspace switch; invite/accept/revoke; memberships and brand grants |
| Brands | Create/read/update brand; brand profile versions; preview/approve voice sample |
| Sources | POST upload-intents; POST source/{id}/finalize; POST from-url; GET source; process/cancel; transcript versions and alignment |
| Packages | Create/read; create version; review; approve/reject exact version; list dependencies |
| Plans | Generate proposal; create edited version; estimate; approve; execute approved version |
| Assets | Read/list; create version; regenerate selected components; review/approve; request rendition/export |
| Video | Scene/timeline versions; preview; clip candidates; approved clip selection and crop |
| Jobs | Read steps/attempts; retry safe failures; cancel; operator reconciliation |
| Connections | OAuth start/callback; capabilities; validate; disconnect |
| Publications | Create intent; revise; approve; schedule; pause/cancel; status; authorized takedown request |
| Analytics | Metric queries; conversion ingestion; usage/reservations |
| Administration | Entitlements/budgets; export/delete workspace; audit and notifications |

API schemas MUST be implemented and committed before the corresponding milestone UI. Use typed enums and structured errors: code, message, field_errors, retryable, correlation_id. Status codes: 401 unauthenticated, 403 prohibited action, 404 inaccessible object, 409 conflict/stale version, 422 invalid input/state constraints, 429 rate limit. Budget blocks use a documented BUDGET_EXCEEDED code consistently.

All billable or publishing mutations require an Idempotency-Key. Scope it to workspace/actor/operation; store normalized request hash and original response. Same key with different input returns 409. Retain billable/publication operation identity indefinitely through the relevant ledger retention period; ordinary request replay cache defaults to seven days. Optimistic edits use If-Match/version ID; stale clients must reload or merge, not overwrite.

Event envelope:

```json
{
  "event_id": "uuid",
  "schema_version": 1,
  "type": "asset.version_created",
  "occurred_at": "ISO-8601 UTC",
  "workspace_id": "uuid",
  "aggregate_id": "uuid",
  "aggregate_version": 2,
  "correlation_id": "uuid",
  "data": {}
}
```

Required event families: source.*, package.*, plan.*, asset.*, job.*, review.*, publication.*, metrics.*, usage.*, connection.*. Outbound webhooks, if enabled, use HMAC signatures, timestamps and event IDs; default five-minute timestamp tolerance. Inbound callbacks use the provider-supported verification mechanism and duplicate protection; never invent an HMAC requirement that a provider does not implement. Reconcile remote identifiers against known local attempts before updating tenant data.

## 17. UX requirements

Primary navigation: Home, Create, Content Library, Review, Calendar, Analytics, Brands/Settings. Workspace switching is always visible. Do not expose implementation tables as unrelated product tabs.

Create flow: starting source → strategy → package review → asset plan and estimate → production/review → schedule or download. Users can save and resume. Required fields have useful defaults and clear explanations. The interface must support text-only creation without empty video requirements.

Production view shows actual stages, elapsed time, outputs ready, blockers and next action. Do not fabricate percentage completion. A partial campaign provides “retry failed,” “review ready,” and “download ready” actions.

Review view includes claim/source evidence, diff against prior version, scene/timecode comments, approvals and stale warnings. Calendar supports list/week views, timezone display, destination filtering, move/pause and conflict messages. Dragging an item creates a revised pending schedule, not an unapproved live update.

In-app notifications are required for review requests, failures, connection expiry, budget blocks and late schedules. Email notifications are optional until a mail provider and sending authority are configured. Keyboard operation, labeled inputs, contrast and caption controls must be included in acceptance review.

## 18. Analytics, attribution and learning

R1 dashboard shows production throughput, review status, spend, publications and native metrics available from each connection. Store provider/native metric name, definition/version, period, retrieved_at and availability. Missing is null/unavailable, never zero. Cumulative snapshots are not summed as new interval activity.

Conversion ingestion is optional to configure but the endpoint and deduplication contract are required. Accept external event ID, source, type, occurrence time, campaign/publication/CTA references when known, value and currency. Unique key: workspace + source + external event ID. Verify referenced IDs belong to the tenant. Do not require personal data when an external pseudonymous reference suffices.

A lead, appointment and purchase may be stages for one person; report distinct leads separately. Preserve event occurrence and ingestion times. Unattributed events remain unattributed. Do not claim causal revenue attribution from UTMs or infer component performance from aggregate video success.

R3 learning produces reviewable recommendations with sample, time window, comparable items, limitations and versioned application history. No autonomous strategy changes in R1. Client data is not pooled into another client's retrieval or learning without a separately approved sharing policy.

## 19. Security, privacy, retention and operations

Unpublished media is private. Signed access URLs default to ten-minute lifetimes; provide longer purpose-limited provider retrieval windows only when required and record them. Download archives are private and expire. Non-guessable paths are not a substitute for authorization.

Scan uploads and isolate parsers/transcoders with resource and execution limits. Do not execute uploaded macros or scripts. Sanitize rendered HTML and treat prompt content, source files and provider responses as untrusted. Tools cannot be granted by instructions embedded in source content.

Proposed retention defaults: retain originals and approved outputs until owner deletion or quota action; clean temporary proxies after 30 days of inactivity; delete prepared archives after seven days. Audit/usage records retained 12 months by default with sensitive payload minimization. Deletion tombstones stop jobs and publication immediately; active-store purge target seven days, backup expiry target 35 days. Validate provider deletion capabilities and disclose exceptions in admin status. These are configurable operational defaults, not legal retention advice.

Maintain daily database backups and object recovery strategy. Proposed R1 recovery objectives: <=24 hours data loss and <=8 hours restore time, demonstrated in a drill. Host choice remains an M0 ADR; do not migrate merely because earlier documents mentioned another platform.

Performance targets on a documented pilot-size dataset: 20 concurrent interactive users across two workspaces; p95 ordinary API reads <=1 second and job acknowledgements <=2 seconds excluding upload/provider time; runnable jobs normally claimed within 30 seconds; scheduled dispatch starts within 60 seconds of target under normal operation. Measure media completion by duration/provider and show estimates; no guaranteed end-to-end render duration before benchmarking.

CI must run schema validation, unit/integration tests, PostgreSQL migrations and a frontend build. Use a separate disposable test database. Tests that call drop_all must never inherit a production DATABASE_URL. Deployment must not mutate schema indiscriminately at every application startup.

## 20. Milestones and gates

| Milestone | Deliverables | Gate |
|---|---|---|
| M0 — Inventory and contracts | Current commit inventory, local setup, baseline tests, ADRs, provider/account capability matrix, API/schema plan | Reproducible baseline; simulated state labeled; external dependencies visible |
| M1 — Secure foundation | OIDC/session setup, memberships/grants, migrations, private upload shell, durable jobs/outbox, budget reservations | Isolation, concurrency, restart and migration tests pass on PostgreSQL |
| M2 — Package and text slice | Text/PDF/DOCX ingestion, research/evidence, versioned package/plan, text outputs, review/export | Topic and file produce real-provider approved written assets with lineage |
| M3 — Human video slice | Media upload/probe/transcription, transcript corrections, clip selection/editing, captions/renditions | Real recording produces reviewed main output plus selected moments and four delivery profiles |
| M4 — Avatar slice | Consent, script/scene review, real HeyGen, assembly, B-roll replacement, partial regeneration | Approved package produces playable avatar output; usage reconciled |
| M5 — Scheduling/connectors | Calendar, five direct adapters, OAuth, dispatch/reconciliation, downloads | Controlled authorized real publication on each destination; no simulated success counted |
| M6 — Pilot acceptance | Metrics, notifications, deletion/export, restore drill, team UAT, operating runbook | Both teams complete core workflows; all R1 acceptance gates pass |
| M7 — SaaS expansion | Signup, billing, entitlements lifecycle, subscriber operations | Separate R2 commercial specification approved and tests pass |

Independent provider-access applications may run during M0 while implementation continues. Do not defer discovery of account limitations until M5. M0–M4 can produce usable previews but do not constitute full R1 acceptance. No fixed completion date is asserted; Astra reports milestone estimates after M0 evidence.

## 21. Acceptance suite

Each test must identify fixture, action, expected persisted state and evidence artifact. Tests of external behavior use sandbox/recorded contracts during development and authorized real-provider gates before release.

| ID | Scenario | Required result |
|---|---|---|
| AT-01 | User from workspace A attempts IDs/search/export/jobs in B | No data or mutation; no signed URL leakage |
| AT-02 | Editor attempts approval or publisher edits content | Forbidden unless separately granted role |
| AT-03 | Topic and document create packages | Same schema; sources and claims retained; real text output |
| AT-04 | Approved package edited after scheduling | New version, affected assets stale, schedules paused |
| AT-05 | Two workers contend for remaining budget | Atomic cap respected; no lost settlement |
| AT-06 | Worker dies after provider accepts submission | Reconciliation; no blind duplicate submission |
| AT-07 | Lease expires and old worker returns | Fencing prevents stale commit |
| AT-08 | Duplicate/out-of-order callback | One logical outcome/settlement; no terminal state regression |
| AT-09 | Cancel partly completed campaign | Unsent steps stop; real incurred spend retained; ready outputs accessible |
| AT-10 | One video fails among successful text assets | Partial success; retry does not replace good assets |
| AT-11 | Transcript corrected around clip boundary | Original preserved; valid alignment; actual clip matches selection |
| AT-12 | Model returns fabricated evidence URL | Unsupported claim remains blocked for correction/review |
| AT-13 | Consent revoked before scheduled dispatch | Dispatch blocked; affected outputs surfaced |
| AT-14 | Publish response lost | RECONCILING, not automatic duplicate or false live status |
| AT-15 | Connection revoked or token expired | Safe refresh or user-action state; no account substitution |
| AT-16 | Schedule misses time by >15 minutes | Paused and notified |
| AT-17 | Ambiguous daylight-saving time | Explicit correction required; no silent interpretation |
| AT-18 | Repeat conversion event and funnel stages | Deduplicated event; unique leads not inflated |
| AT-19 | Locked scene plus unrelated revision | Locked work preserved; cost estimate reflects actual regeneration |
| AT-20 | Invalid upload/URL to internal host | Rejected safely with useful error; no unauthorized fetch |
| AT-21 | Real avatar and human videos | Playable files, accurate captions/ranges, complete version lineage |
| AT-22 | Four short-form destinations | Correct rendition/profile and per-platform metadata for selected moments |
| AT-23 | Five direct publishing destinations | Verified authorized publications; remote identity and visibility recorded |
| AT-24 | Export without social connection | Usable archive; no “published” status assigned |
| AT-25 | Backup restore | Application records, media references, approvals and job recovery demonstrated |
| AT-26 | Workspace deletion | Work stopped; active-store purge tracked; backup/provider exceptions visible |
| AT-27 | Production provider unavailable | Typed blocked/failure state; no automatic simulated fallback |
| AT-28 | Same idempotency key, different request | Conflict; no new side effect |
| AT-29 | Zero budget | All paid calls blocked; no fallback spending allowance |
| AT-30 | Malicious instructions embedded in source | Treated as content; cannot access tools/secrets or change authorization |

Editorial evaluation set: at least 10 permitted representative sources covering idea, document, human recording and avatar script, including both pilot brands. Product owner supplies or approves fixtures. Score factual alignment, voice, format suitability, clip coherence and edit burden on a defined 1–5 rubric. Proposed pass: each dimension average >=4, no source below 3, and zero critical factual/rights failures. Approval of the rubric and samples is an M2 gate, not a reason to stop M0/M1.

## 22. Astra execution instructions

1. Read this specification and applicable repository instructions. Inspect the current branch and commit before editing. Record the baseline and discrepancies.
2. Create an isolated working branch following repository policy. Do not overwrite unrelated changes or existing data.
3. Replace conflicting scope documentation through a reviewable change; preserve history. This specification is the product target, not evidence of implemented features.
4. Implement M0, then M1 through M6 in dependency order. Advance only when the relevant gate passes or is explicitly documented as externally blocked; never label a blocked release complete.
5. For each milestone, implement schema/API/UI/worker behavior together where needed to demonstrate a vertical workflow. Do not build a decorative UI over placeholders and call it done.
6. Use deterministic fixtures and contract tests for development. Production mode must fail visibly when a provider is not implemented/configured; simulation requires explicit development configuration and visible labels.
7. Require configured spending authorization before paid tests and explicit publication authorization before real external posts. Continue all independent work while access is pending.
8. Maintain BUILD_LOG.md with requirement IDs, changed files, tests run, real/simulated distinction, output references and remaining blockers. Update CURRENT_STATE.md after each milestone.
9. Commit coherent changes with migrations and meaningful tests. Open a reviewable draft PR where authorized by the execution environment. Do not merge or deploy solely because this document says the build is ready.
10. Report outcome, evidence, risks and next milestone. Do not silently remove functionality to make tests pass or replace direct integrations with exports.

Required engineering documents generated during implementation: CURRENT_STATE.md; ADRs; OpenAPI and event schemas; migration plan; provider capability matrix; acceptance evidence; DEPLOYMENT.md with backup/restore and rollback; BUILD_LOG.md. These must correspond to code and tests, not duplicate aspirational prose.

### Starter instruction to paste into Astra

> Implement Content OS using CONTENT_OS_ASTRA_BUILD_SPEC_v6.md as the product contract in https://github.com/zialcita/content-os. Start at M0 by verifying the repository and producing a commit-specific baseline. Preserve existing data and reusable code. Implement milestones in order with real acceptance evidence, durable execution, versioned approvals and tenant isolation. Distinguish simulated fixtures from live integrations. Continue routine engineering work autonomously; report specific external gates without weakening the requirements. Do not publish, incur unapproved provider costs, merge or deploy without the applicable authorization.

## 23. Remaining external gates and defaults register

These do not prevent beginning repository work. Resolve each before its dependent action.

| Gate | Owner | Needed by | Safe behavior until resolved |
|---|---|---|---|
| Verified current repository/environment access | Astra / Martin | M0 | Read-only inventory and local fixtures |
| OIDC provider and deployment project | Astra proposes; Martin supplies account access | M1 integration | Local development identity only, clearly labeled |
| Actual brand members and reviewer | Martin / Tailor Law representative | Team onboarding | No invented invitations or reviewer identities |
| HeyGen avatar/voice and consent | Authorized owner | M4 real render | Script/scene preview and contract tests |
| AI/transcription/assembly/storage credentials | Workspace/platform owner | Relevant real-provider gate | No fabricated provider results |
| Positive production budget and spending cap | Martin/workspace owner | First paid operation | Zero live spend |
| Social account identity/type and app access | Authorized account owners | M5 | Exports and clearly blocked connector status |
| Permission for controlled test publications | Authorized publisher | M5 real gate | Drafts and validated payloads only |
| Brand evaluation samples/rubric | Martin and brand reviewers | M2/M6 | Generic development fixtures cannot satisfy brand acceptance |
| Retention defaults and host operational settings | Owner with Astra recommendation | Production release | Use documented defaults in development; no unreviewed destructive purge |
| Subscriber pricing/billing policy | Martin | R2 | Admin entitlements; no public paid signup |

Client workspace interpretation, English-first support, input limits, role defaults, retention, concurrency and export defaults are proposed choices in this specification. Surface requested changes through a versioned decision record. No engineering deadline or financial commitment is fabricated.

## 24. Definition of completion

R1 is complete when AI Marketing Box and Tailor Law users can securely operate their own workspaces; start from a topic/document or human recording; produce approved written assets and avatar/human video; select 3–5 viable moments and adapt them for four short-form channels; review and edit; schedule through five real social connections; download usable files; and inspect status, lineage, available metrics and actual usage.

All required acceptance scenarios must pass or have an explicit product-owner-approved scope change. External access failure is a blocker, not a passing result. The repository must include deployable code, migrations, operating instructions and retrievable test/output evidence.

**End of specification — Version 6.0**
