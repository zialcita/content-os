# Content OS v6 — acceptance matrix and evidence contract

Current status update (2026-09-11): the M0 local gate is satisfied; frontend install/build now pass and npm audit reports zero vulnerabilities after the verified PostCSS patch. M1 component evidence is available in M1_PROGRESS.md (44 PostgreSQL foundation,59 runtime safety,42 contract and5 isolation tests passed). These provide partial local coverage of named AT obligations, not full end-to-end scenario or release completion. Full AT verdicts below remain NOT RUN/OPEN. Original evidence descriptions and blocked-network notes below are preserved historical context.

**M0 planning artifact. All AT-01–AT-30 status: NOT RUN.** This is a test specification, not execution evidence. Authority: [v6 master](spec/CONTENT_OS_ASTRA_BUILD_SPEC_v6.md), read fully, especially §§20–24. Companion implementation tickets: [MILESTONE_BACKLOG.md](MILESTONE_BACKLOG.md). Proposed persistence/API boundaries: [DATABASE_DESIGN.md](DATABASE_DESIGN.md), [API_CONTRACTS.md](API_CONTRACTS.md). Preserve the master's AT identifiers; supplemental gates below add coverage without replacing or renumbering them.

## 1. Verdict and evidence rules

- **NOT RUN** means no qualifying run proves this acceptance scenario. A dependency can be BLOCKED while the AT remains NOT RUN. After actual execution use PASS/FAIL for the tested phase, with BLOCKED for missing mandatory live/human gate. Never turn a local/simulated pass into a full release pass.
- **L**: deterministic local/contract/fault test, using disposable PostgreSQL for persistence/concurrency/migrations; **V**: authorized real provider/account/environment verification; **H**: named authorized human review/decision. Required modes are specified per AT. They are separate evidence fields, not interchangeable tiers.
- Three legacy SQLite tests passed with explicitly simulated providers and empty credentials (`docs/evidence/m0/safe-baseline-summary.json`, `safe-baseline-pytest.log`). They satisfy **no AT**. The real PostgreSQL 16.2 initialization log (`postgres-baseline.log`) says vector is available and legacy `init_db` succeeded; it proves neither applied v6 migrations nor tenant/concurrency behavior. `postgres-pytest.log` has three legacy successes but does not by itself prove the tests did not override the DB URL. Do not credit it toward an AT.
- `contracts-unittest.log` reports 25 offline schema/policy tests OK; `openapi-validation.log` reports structural PASS. API_CONTRACTS also records an earlier 23-pass/2-skip run. Neither tests runtime behavior. All proposed endpoints and schemas remain planned until implementation proof.
- Frontend `npm ci` is **blocked E403** on the registry; `frontend-build.log` reports `next: command not found`. Owner/network permission is required; no bypass. M0 is **PARTIAL / NOT ACCEPTED**, not passed automatically by creating these documents.
- Every run needs: run ID, UTC start/end, actual commit/branch/dirty-tree status, command/test selector and exit status, dependency/DB versions, fixture IDs/hashes/rights, actor/tenant/brand scope, mode, approved budget and publication authority when applicable, request/response and event correlation IDs, pre/post persisted assertions, output hashes/retrievable references, expected vs observed results and reviewer/operator sign-off.
- Future paths below are required artifacts under `docs/evidence/mN/AT-XX/<run-id>/`, **not existing evidence**. Each bundle includes `run.json`, `assertions.json`, redacted `trace.jsonl`, and scenario-specific files listed. `run.json` links stage results across milestones. Screenshots alone, placeholder URLs and mock-only successful outputs never prove acceptance. Keep private files private; use authorized durable object references, not expired signed links or tokens in logs.
- Local adversarial fixtures never use production DB/credentials. Require positive disposable-DB verification before destructive tests; never inherit production DATABASE_URL into drop/reset tests. Paid production defaults to zero. A LIVE-mode outbound spy can prove a blocked call locally without real credentials; that is not a real-provider success.
- External gate owners/needed-by dates are tracked as dependencies, **not invented deadlines**. G-ENV/IDENTITY/PEOPLE/EDITORIAL/PRODUCTION/BUDGET/SOCIAL/PUBLISH/OPS/R2 are defined in the backlog. Wait is unbounded. Downloads never replace direct publication. No social scopes, eligible account type or app approval are inferred from a configured key.

## 2. Fixture catalog (to create/approve, not claimed present)

| Fixture | Reproducible contents and authority |
|---|---|
| **F-TENANT** | Disposable PG with workspaces A/B, two brands in A and one in B; verified development test identities for owner/admin/editor/reviewer/publisher/viewer and combined roles, explicit grants and a revoked member. Clearly labeled test identities, not real invitations. Separate owner-authorized real identities for V/H and both-team UAT. |
| **F-VERSIONS** | Canonical approved package P1, exact plan/estimate/recipe/profile, written assets, approved final cut/rendition and distinct publication revision/approval; unrelated locked asset, one live-history fixture labeled simulated. All UUIDs same-tenant except deliberate negative requests. No use of `latest`. |
| **F-JOBS** | Durable worker harness with two independent processes, barrier-controlled clock/network proxy, stub remote operation registry and known accepted/not-accepted/unknown outcomes; deterministic event IDs, budgets and crash hooks. Attempts tagged development simulation; isolated real-adapter repetitions only when authorized. |
| **F-TEXT** | Permitted topic/opinion plus factual brief, PDF with pages, DOCX with paragraphs/tables, public article snapshot, Unicode names and adversarial evidence/instruction variants. Hash/locator/rights manifest. Real editorial examples approved under F-EDITORIAL. |
| **F-MEDIA** | Rights-cleared real human recording with speakers, qualifying language at chosen clip boundary and known timecodes; audio/video formats, valid/invalid SRT/VTT, corrupt/overlimit variants, source hash and manual reference transcript. No simulated URLs as playable output. |
| **F-AVATAR** | Owner-authorized avatar/voice identifiers and consent artifact, approved script/scene plan with named pronunciation cases, licensed B-roll and a locked scene; exact approved plan/cap before any paid render. |
| **F-SOCIAL** | Approved final media/text versions and profiles; one explicitly authorized eligible account per required destination, plus YouTube long/Shorts variants; capability/app/scopes evidence and controlled-post approval for exact account/content/visibility/schedule. Local contract fixtures exist separately and confer no posting authority. |
| **F-OPS** | Documented pilot-size data generator and private object manifest, approved backups, tombstone workspace, queued/running/uncertain jobs and immutable approvals/usage. Disposable recovery target, operation timestamps and external acceptance registry for reconciliation. |
| **F-EDITORIAL** | >=10 owner-approved representative permitted sources spanning idea, document, human recording and avatar script, including AI Marketing Box and Tailor Law. Source rights/consent and exact evaluation versions; actual brand reviewers selected by authorized people, not invented. See SG-EDITORIAL. |

## 3. AT-01–AT-30 executable acceptance specifications

### AT-01 — Cross-workspace and brand isolation
- **Status:** NOT RUN. **Milestones/tickets:** M1-01/02/05 first; M2 search/export, M5-01 callbacks, M6-02/04 full regression. **v6:** §§7,8.1,10,16,19,21 AT-01.
- **Fixture/action:** F-TENANT plus B's source/package/job/publication/private object. As A user, attempt known B IDs through GET/PATCH, search, list cursor, export, job retry/cancel and signed URL issuance. Also try ungranted A brand, cross-tenant FK writes, pooled connection reuse, forged callback tenant and revoked worker requester.
- **Expected persisted state:** No B content/permission/version/job/publication/ledger mutation; no export job/object URL issued. Inaccessible objects return 404; prohibited known actions 403. Tenant composite FKs/RLS reject references; missing/reset context denies. Callback cannot choose tenant. Only minimal authorized security audit records may be added.
- **Evidence:** `docs/evidence/m1/AT-01/<run-id>/isolation-matrix.json`, pre/post row/hash counts and redacted HTTP/worker traces; final matrix M6. **Gate:** L PG + authenticated UI verification; no real client data needed for adversarial requests.

### AT-02 — Role separation
- **Status:** NOT RUN. **Milestones/tickets:** M1-02; M2-02, M5-02, M6-04 reruns. **v6:** §§2.2,7,9,16,21 AT-02.
- **Fixture/action:** F-TENANT with editor-only and publisher-only memberships/grants and an exact asset/package version. Editor calls approval endpoints; publisher edits package/script/asset. Try admin self-ownership promotion. Repeat with explicitly combined reviewer/editor and publisher/editor grants, then revoke the extra role.
- **Expected persisted state:** Forbidden attempts 403 with no approval/content/ownership mutation or provider intent. Only separately granted actions succeed; approval actor/scope/version and role audit are persisted. Admin never becomes owner by role edit. Revocation blocks subsequent attempts, including queued work.
- **Evidence:** `docs/evidence/m1/AT-02/<run-id>/role-action-grid.json`, decisions/version hashes before/after and UI/API traces. **Gate:** L PG; H actual Tailor Law reviewer designation validated in M6, not fabricated by test setup.

### AT-03 — Topic and document produce real written packages
- **Status:** NOT RUN. **Milestones/tickets:** M2-01/02/03/04; final M6-04. **v6:** §§5.1–5.2,6.1–6.2,8.3,10,11,21 AT-03.
- **Fixture/action:** F-TEXT and approved F-EDITORIAL topic + PDF/DOCX examples for both brands. Configure authorized AI/retrieval and budget; submit topic and file, inspect claims/source excerpts, approve exact package/plan and generate/review LinkedIn post/article/newsletter without avatar configuration.
- **Expected persisted state:** Same canonical package schema on both paths, source hashes and page/paragraph locators/claims/atoms retained; exact brand/recipe/model/prompt/plan dependencies; separate immutable human approvals; real output text with format-specific structure, newsletter subject/preheader/CTA and truthful usage. Unsupported high-severity claims cannot become approved.
- **Evidence:** `docs/evidence/m2/AT-03/<run-id>/package-lineage.json`, source/output hashes, redacted real provider request IDs, written files, review and ledger records. **Gate:** L + V G-PRODUCTION/G-BUDGET + H G-EDITORIAL; mock text alone cannot pass.

### AT-04 — Package edit invalidates scheduled derivatives
- **Status:** NOT RUN. **Milestones/tickets:** M1-01 primitives, M2-02 fixture, M5-02 integrated scheduling, M6-04 final. **v6:** §§8.1,9,13,15.2,16,21 AT-04.
- **Fixture/action:** F-VERSIONS scheduled on P1 plus unrelated asset and previously-live historical record. Change thesis/claim/CTA to P2 via If-Match; race a scheduler and finish an old-version job. Repeat with stale ETag.
- **Expected persisted state:** New immutable P2/current pointer; affected unpublished assets stale, exact decisions preserved but invalidated for dispatch, schedules PAUSED and outbox/invalidation barrier persisted. Unrelated asset unchanged; already-live history preserved with correction/takedown review item. Old job result stays on P1 and inherits no P2 approval. Stale request 409 makes no mutation; unsent dispatch blocked, in-flight uncertainty reconciled rather than denied historically.
- **Evidence:** `docs/evidence/m5/AT-04/<run-id>/dependency-diff.json`, version/decision/queue snapshots and race traces. **Gate:** L PG; H approve correction if actual live content is used, otherwise clearly simulated history fixture.

### AT-05 — Concurrent remaining-budget reservation
- **Status:** NOT RUN. **Milestones/tickets:** M1-04; M6-03 regression. **v6:** §§13,14,16,21 AT-05.
- **Fixture/action:** F-JOBS on PG: all caps configured, restrictive remaining cap 100 micro-units, two workers each request 80. Synchronize reserve calls; repeat with restrictive workspace/campaign/job/plan cap, duplicate settlement, settle-vs-release and mismatched currency.
- **Expected persisted state:** Exactly one eligible reservation and submission intent, other receives BUDGET_EXCEEDED without side effect. Cap allocation counters/immutable ledger reconcile with no lost settlement or negative reservation. Duplicate callbacks settle once; uncertain outcomes retain reservation. Real overrun records debt and blocks further spending, not discarded to make test green.
- **Evidence:** `docs/evidence/m1/AT-05/<run-id>/concurrency-ledger.json`, PG transaction/barrier logs, account/reservation/ledger queries. **Gate:** L on real PG, not SQLite; simulated charges cannot settle as LIVE provider spend.

### AT-06 — Crash after provider acceptance
- **Status:** NOT RUN. **Milestones/tickets:** M1-03/04 local; M4-02 real production, M5-03–07 publishing adapters. **v6:** §§13,14,15.2,16,21 AT-06.
- **Fixture/action:** F-JOBS commits intent; controlled provider accepts then worker is killed before local response/result commit. Restart API/worker/database as applicable. Reconcile by known remote request/dedupe identity; repeat unknown and proven-nonacceptance variants.
- **Expected persisted state:** Expired accepted/unknown attempt enters RECONCILING with retained reservation and one logical operation. No automatic second submission. Verified outcome links one output/settlement; unknowable status retains operator-resolution task. Retry only with established nonacceptance or provider-verified safe dedupe; old fencing token cannot commit.
- **Evidence:** `docs/evidence/m1/AT-06/<run-id>/crash-timeline.json`; M4/M5 per-adapter real acceptance/status and provider billing references plus fault-proxy trace. **Gate:** L + V adapter proof under authorized spend/post; unknown provider semantics keep live gate blocked, not assumed exactly-once.

### AT-07 — Expired worker cannot commit
- **Status:** NOT RUN. **Milestones/tickets:** M1-03; M6-03. **v6:** §§4,13,16,21 AT-07.
- **Fixture/action:** F-JOBS worker W1 acquires fence N, pauses beyond expiry; reaper/W2 advances fence. Return W1 with result, heartbeat, settlement and outbox writes; also test expired lease before reaper has run.
- **Expected persisted state:** W1 renewal/result transaction rejected using owner/token/state/unexpired lease guard; no child output, money settlement, transition or event partially commits. W2 alone advances state; stale observation may be stored only as non-authoritative reconciliation input. No Redis lock dependency.
- **Evidence:** `docs/evidence/m1/AT-07/<run-id>/fence-assertions.json`, lease/token transitions and pre/post output/ledger/outbox counts. **Gate:** L PostgreSQL with two processes and controlled clock/barriers; status-row-only fencing is insufficient.

### AT-08 — Duplicate and out-of-order callback
- **Status:** NOT RUN. **Milestones/tickets:** M1-03/04; M4-02 and M5 adapters. **v6:** §§13,14,15.2,16,21 AT-08.
- **Fixture/action:** F-JOBS known accepted attempt. Deliver provider-verified success twice, older processing after success, same event ID/different hash, invalid verification and unknown remote ID. Re-deliver internal outbox event after relay crash. Use each provider's actual verification, not invented universal HMAC.
- **Expected persisted state:** Inbox uniqueness and guarded transition yield one logical output/settlement, no terminal regression. Mismatched/unverified/unknown events are rejected/quarantined, cannot alter arbitrary tenant data. Outbox/inbox application is transactional; legitimate out-of-order observations retained without regressing outcome.
- **Evidence:** `docs/evidence/m1/AT-08/<run-id>/callback-order-grid.json`; M4/M5 sanitized provider callback/status evidence and inbox/ledger uniqueness queries. **Gate:** L + V provider callback/polling verification capability. Unsupported callbacks use verified reconciliation, not a fictitious pass.

### AT-09 — Cancel partly completed campaign
- **Status:** NOT RUN. **Milestones/tickets:** M1-03/04, M2-03; repeat M4-02/M6-04. **v6:** §§5.5,13,14,17,21 AT-09.
- **Fixture/action:** F-JOBS with completed text, an accepted paid video render, queued derivative and a ready export. Cancel campaign while provider work is in flight; provider later reports success/charge. Try retrying cancelled unsent work.
- **Expected persisted state:** Unsent steps cancelled/stopped; in-flight attempt reconciles true remote outcome under allowed state transitions, downstream remains blocked. Real incurred usage remains SETTLED/adjusted, not refunded by cancel. Ready asset/version/hash and authorized downloads remain accessible; aggregate cancellation/partial detail visible. No new production intent after cancellation.
- **Evidence:** `docs/evidence/m2/AT-09/<run-id>/cancel-manifest.json`; M4 real charge reconciliation, step states, output hash comparisons and UI actions. **Gate:** L + V paid cancellation semantics under G-BUDGET; user may accept actual cost, no refund promise.

### AT-10 — Failed video preserves successful text
- **Status:** NOT RUN. **Milestones/tickets:** M1-03, M2-03, M4-02, M6-01/04. **v6:** §§5.5,9,11,13,17,21 AT-10.
- **Fixture/action:** F-VERSIONS portfolio has successful approved LinkedIn/article/newsletter and one video that fails a safe retryable stage. Use “retry failed” on that video, review/download ready text throughout, then complete video or reach permanent failure.
- **Expected persisted state:** Campaign PARTIAL_SUCCESS while appropriate; failed step/error/action visible independently. Text IDs, hashes, decisions and usage unchanged; retry creates only required video attempts/new dependent versions, respecting budget and exact input bindings. No regeneration or replacement of successful unrelated assets.
- **Evidence:** `docs/evidence/m2/AT-10/<run-id>/partial-output-diff.json`, before/after asset/approval/job rows and UI/download checks; M4 adapter repetition. **Gate:** L + real-adapter integration at M4; simulated partial flow alone is not full media evidence.

### AT-11 — Transcript correction at clip boundary
- **Status:** NOT RUN. **Milestones/tickets:** M3-01/02/03; M6-04. **v6:** §§5.3,9,10,12.2,12.4–12.5,21 AT-11.
- **Fixture/action:** F-MEDIA contains a qualifier near selected in/out and known reference timecodes. Correct presentation text/split segment; try production with uncertain alignment, then realign or explicitly confirm timing, preview bounds and render selected clip.
- **Expected persisted state:** Original spoken transcript/media hash unchanged; new transcript version and stable segment lineage distinguish spoken from corrected text. Affected derivatives invalidated; clip blocked until valid alignment/manual confirmation recorded. Clip binds approved final cut/package and corrected alignment, actual media timing matches chosen bounds without losing qualifier or clipped words.
- **Evidence:** `docs/evidence/m3/AT-11/<run-id>/alignment-diff.json`, original/corrected transcript, frame/timecode validation, real clip hash and human review. **Gate:** L + V real transcription/media + H meaning/boundary check, G-PRODUCTION/G-BUDGET/source rights.

### AT-12 — Fabricated evidence URL blocked
- **Status:** NOT RUN. **Milestones/tickets:** M2-01/02/04; M6-04. **v6:** §§8.3,10,11,21 AT-12.
- **Fixture/action:** F-TEXT model output injects plausible nonexistent URL as support for high-severity factual/legal claim. Attempt final approval, including falsely marking supported and reviewer reclassification without reason; then correct against a retrievable permitted excerpt.
- **Expected persisted state:** Claim remains unsupported/unreviewed with no valid fabricated evidence relationship; approval rejected until corrected or legitimate reclassification with reviewer reason. No invented evidence is accepted even by reviewer. Corrected version stores locator/retrieval/snapshot and immutable decision; original invalid claim preserved historically. Tailor Law substantive claims need jurisdiction/designated review.
- **Evidence:** `docs/evidence/m2/AT-12/<run-id>/claim-verification.json`, retrieval failure/correction trace, claim/evidence/decision rows. **Gate:** L deterministic adversarial fixture + H substantive review; real text workflow proof covered by AT-03.

### AT-13 — Consent revoked before dispatch
- **Status:** NOT RUN. **Milestones/tickets:** M4-01, M5-02; M6-04. **v6:** §§7,9,12.3,15.2,21 AT-13.
- **Fixture/action:** F-AVATAR/F-SOCIAL approved scheduled asset uses consent C1. Revoke before dispatch authorization, advance time and run scheduler; also test before render and after a submission has already entered in-flight region.
- **Expected persisted state:** Append-only consent event/policy epoch and invalidations; unsent render/publication blocked or PAUSED, affected items/review notices surfaced, no new provider intent. Existing live history opens review, not silently deleted. Already transmitted operation reconciles/cancels where supported and records truth; no claim that revocation undid remote acceptance.
- **Evidence:** `docs/evidence/m5/AT-13/<run-id>/consent-dispatch-race.json`, consent/version/queue rows and outbound-call count. **Gate:** L plus authorized consent workflow H; any real in-flight test requires G-BUDGET/G-PUBLISH and provider cancellation capability proof.

### AT-14 — Publish response lost
- **Status:** NOT RUN. **Milestones/tickets:** M5-02/03/04/05/06/07; M6-03/04. **v6:** §§13,15.1–15.3,16,21 AT-14.
- **Fixture/action:** F-SOCIAL per adapter; proxy lets authorized publish be accepted then drops response. Restart dispatcher and request status/retry. Test unknown result and later confirmed live with requested visibility.
- **Expected persisted state:** One logical publication and unresolved attempt in RECONCILING; no automatic duplicate upload/post, no false PUBLISHED. Only verified remote state/visibility can set PUBLISHED with remote account/ID/observed time. Unknown keeps reservation/owner/operator blocker; intentional repost requires separate approved intent. Upload ID alone remains PROCESSING.
- **Evidence:** `docs/evidence/m5/AT-14/<run-id>/per-destination-reconciliation.json`, redacted network fault trace, durable attempts and authorized remote verification; billing if incurred. **Gate:** L + V/H for all required adapters under G-PUBLISH; recorded contracts develop logic, cannot prove actual provider dedupe.

### AT-15 — Expired or revoked connection
- **Status:** NOT RUN. **Milestones/tickets:** M5-01–07, M6-01/04. **v6:** §§7,15.1–15.2,16,17,21 AT-15.
- **Fixture/action:** F-SOCIAL scoped connection with expired token, revoked token and denied/missing required grant variants. Run validation/dispatch; exercise refresh only where provider supports it. Include another valid account to detect silent substitution.
- **Expected persisted state:** Safe refresh updates encrypted credentials for same verified identity or connection becomes typed blocked/user-action state; pending work pauses/notifies. No switch to another account, no token/signed URL in logs, no repeated unsafe submission. Current scopes/app restrictions remain explicit; credential presence alone not authority.
- **Evidence:** `docs/evidence/m5/AT-15/<run-id>/connection-failure-grid.json`, redacted refresh/status trace, connection/publication/notification assertions. **Gate:** L + V actual authorized refresh/revocation validation per destination, H reconnect if required; account review waits are blockers.

### AT-16 — More than fifteen minutes late
- **Status:** NOT RUN. **Milestones/tickets:** M5-02, M6-01/03. **v6:** §§15.2,17,19,21 AT-16.
- **Fixture/action:** F-VERSIONS approved schedule T; stop dispatcher, resume at T+15min+1s. Also test at T+15min and within window with revoked approval to distinguish late policy from eligibility. Use persisted resolved UTC and controlled clock.
- **Expected persisted state:** Beyond 15min publication PAUSED, late reason/event/in-app notification persisted, no external submit. At/below threshold dispatch only if every normal approval/authority/rights/media predicate still passes. User reschedule creates revised time/version requiring new approval.
- **Evidence:** `docs/evidence/m5/AT-16/<run-id>/late-policy-boundaries.json`, queue/state/notification timestamps and zero outbound calls for prohibited cases. **Gate:** L PG; G-PUBLISH only if choosing real posts (not needed for safe pause assertion).

### AT-17 — Ambiguous/nonexistent local schedule
- **Status:** NOT RUN. **Milestones/tickets:** M5-02; M6-04. **v6:** §§8.1,15.2,16,17,21 AT-17.
- **Fixture/action:** F-VERSIONS with pinned tzdata, `America/New_York` fold `2026-11-01 01:30` and gap `2026-03-08 02:30`. Submit via API/calendar; provide explicit corrected unambiguous wall time/validated offset where supported, then move calendar item.
- **Expected persisted state:** Ambiguous/nonexistent requests return typed 422 field error and correction prompt, no silently chosen UTC or dispatchable schedule. Corrected revision stores requested wall time, IANA timezone and resolved UTC consistently, new approval required. Calendar drag cannot mutate existing approved revision into live schedule.
- **Evidence:** `docs/evidence/m5/AT-17/<run-id>/dst-cases.json`, API errors, rendered prompt and publication revisions/approvals. **Gate:** L, no external side effects needed; fixture dates are test inputs, not delivery dates.

### AT-18 — Conversion dedup and funnel stages
- **Status:** NOT RUN. **Milestones/tickets:** M6-01/04. **v6:** §§8.1,16,18,21 AT-18.
- **Fixture/action:** F-TENANT/F-VERSIONS ingest duplicate `(workspace, source, external_event_id)` including concurrent calls; three distinct stage events lead/appointment/purchase share one permitted pseudonymous person reference. Include unlinked event and cross-tenant campaign/publication references.
- **Expected persisted state:** One row per dedupe key; occurrence/ingestion times distinct and values fixed-precision with currency. Lead/appointment/purchase stages do not become three distinct leads. No guessed attribution for unlinked event; invalid tenant references rejected. Metrics preserve native definitions/availability; null not zero, cumulative snapshots not summed.
- **Evidence:** `docs/evidence/m6/AT-18/<run-id>/conversion-aggregation.json`, rows/uniqueness constraints and dashboard query outputs. **Gate:** L; configuring external conversion collection optional, endpoint/dedup contract required. No personal data necessary.

### AT-19 — Locked scene survives unrelated revision
- **Status:** NOT RUN. **Milestones/tickets:** M3-02, M4-01/02/03; M6-04. **v6:** §§9,11,12.1–12.3,14,21 AT-19.
- **Fixture/action:** F-AVATAR script/timeline has locked scene S1, editable S2 and approved reusable render. Change S2 narration/media and request selected regeneration; restore/reject draft variant. Run provider capability variants supporting scene reuse vs requiring full render.
- **Expected persisted state:** New script/timeline/asset versions only as affected; S1 content/hash/lock retained, unrelated assets/approvals untouched. Affected final approval invalidated. Estimate includes actual required regenerated work, with explicit full-render warning before spend if provider cannot do scene-only. Returned output/reuse and actual cost match recorded plan semantics.
- **Evidence:** `docs/evidence/m4/AT-19/<run-id>/locked-scene-diff.json`, capability snapshot, estimate/reservation/actual ledger, output validation. **Gate:** L + V real assembly/regeneration + H preview/cost/script approval; no unsupported scene-level billing promise.

### AT-20 — Invalid upload and internal-host URL
- **Status:** NOT RUN. **Milestones/tickets:** M1-05, M2-01, M3-01; M6-04. **v6:** §§6.1,10,16,19,21 AT-20.
- **Fixture/action:** F-TEXT/F-MEDIA corrupt/MIME-spoof/overlimit/encrypted/scanned-only files; interrupted/cancelled upload and wrong final hash. URL targets loopback/private/reserved/metadata IPv4/IPv6, redirect-to-private and DNS-rebinding under controlled resolver; oversized/decompression/timeouts. Never probe actual internal services.
- **Expected persisted state:** Useful typed rejection/recovery status, quarantine remains unusable, no source clearance/extraction masquerading as complete and no provider job. Controlled network sink proves no prohibited fetch even after redirect/resolution. Bounded resource use/cancellation and within-brand dedup only; no cross-client match disclosure.
- **Evidence:** `docs/evidence/m2/AT-20/<run-id>/input-security-grid.json`, parser/probe/quarantine assertions and controlled egress logs, media cases appended M3. **Gate:** L; private storage real integration separately M1. Passing normal upload alone insufficient.

### AT-21 — Real human and avatar videos
- **Status:** NOT RUN. **Milestones/tickets:** M3-01/02/03 human stage; M4-01/02/03 avatar stage; M6-04 final. **v6:** §§5.3–5.5,6.2,9,12.1–12.5,14,21 AT-21.
- **Fixture/action:** F-MEDIA and F-AVATAR approved fixtures; run real human preserve/edit/caption flow and real HeyGen/assembly flow from exact reviewed package/plan/script, then preview, approve, render and download main/selected clips.
- **Expected persisted state:** Real decodable private files with measured duration/dimensions/FPS/hash, valid captions and source ranges, no unintended blanks, expected audio, correct words/pronunciation/visible essential text. Immutable lineage source/transcript/package/plan/recipe/script/timeline/profile→asset/rendition plus human final decisions and actual/unsettled usage. Human and avatar stage must both pass; one cannot stand for the other.
- **Evidence:** `docs/evidence/m4/AT-21/<run-id>/human-avatar-manifest.json`, ffprobe/decoding/loudness/caption reports, source-range checks, authorized file references and human rubric. **Gate:** L + V paid providers/media + H consent/rights/meaning/names; no placeholder media or screenshot-only proof.

### AT-22 — Four short-form delivery profiles
- **Status:** NOT RUN. **Milestones/tickets:** M3-03, M4-03, M5-03/05/06/07; M6-04. **v6:** §§2.2,5.5,6.2,9,12.4–12.5,15.1,21 AT-22.
- **Fixture/action:** F-MEDIA/F-AVATAR approved final cuts and package. User selects 3–5 distinct coherent moments, sets in/out/manual crop/letterbox and validates each for YouTube Shorts, Instagram Reels, Facebook Page Reels and TikTok. Test five moments and a genuinely short source with explicit fewer-moment acceptance.
- **Expected persisted state:** Selected ranges/rationale/approval linked to reviewed final cut and package, exact profile versions with current official references; four destination metadata sets and eligible renditions per moment. Compatible file reuse permitted, metadata/publication identities stay separate (five moments up to 20 combinations). Shortfall reason persisted, no fabricated filler. Safe zones/text/qualifiers retained.
- **Evidence:** `docs/evidence/m3/AT-22/<run-id>/moment-destination-grid.json`, profile/technical reports and human crop/coherence checks; live validation in M5. **Gate:** L + H and V current account/media compatibility; direct publishing is separately AT-23.

### AT-23 — Five direct publishing destinations
- **Status:** NOT RUN. **Milestones/tickets:** M5-01–07; metrics cross-check M6-01/04. **v6:** §§2.3,5.6,15.1–15.3,18,21 AT-23,24.
- **Fixture/action:** F-SOCIAL with explicit controlled publication approval. Schedule approved outputs through application to **YouTube long-form and Shorts, LinkedIn text, Instagram Reels, Facebook Page Reels, TikTok video**. Observe remote processing/live status/visibility and retrieve metrics where supported.
- **Expected persisted state:** Distinct exact-version intent/revision/approval/attempt per destination; verified authorized account identity/type and actual granted scopes/app status. PUBLISHED only after verified remote ID plus requested visibility/state/time. Native metrics definition/window/retrieved_at/availability persisted; unsupported metric recorded null with official/account evidence. App denial/unsupported desired account remains blocker; never silently substitute account or destination.
- **Evidence:** `docs/evidence/m5/AT-23/<run-id>/five-destination-live-grid.json`, real remote references/status observations, exact approvals, sanitized adapter traces, metric snapshots and cleanup capability/status. **Gate:** V + H G-SOCIAL/G-PUBLISH mandatory for every required destination; download or upload-only handoff cannot pass. Absence of app approval has unbounded wait, not a green exception.

### AT-24 — Export without social connection
- **Status:** NOT RUN. **Milestones/tickets:** M2-03 text, M3-02/M4-03 media, M6-02/04. **v6:** §§5.5–5.6,6.2,7,16,19,21 AT-24.
- **Fixture/action:** F-VERSIONS workspace has no social connection and successful text/media outputs, plus one failed item. Authorized viewer requests asynchronous private archive and downloads it; inspect/unpack files, captions/text/metadata/manifest. Retry expired access and revoked viewer access.
- **Expected persisted state:** Export job and archive manifest pin successful exact versions/hashes; files usable independently, not blocked on failed item or OAuth. Private object access expires and reissuance reauthorizes. No publication/attempt/PUBLISHED state or social spend is created merely by export. Unavailable members clearly identified, not placeholder success.
- **Evidence:** `docs/evidence/m2/AT-24/<run-id>/archive-check.json`, unpacked manifest/hash/media/text checks and publication count diff; complete media bundle M4. **Gate:** L plus actual storage/file usability; H review usability. Exports do not satisfy AT-23.

### AT-25 — Backup restore and job recovery
- **Status:** NOT RUN. **Milestones/tickets:** M1-01 migration recovery rehearsal; qualifying drill M6-03/04. **v6:** §§4,9,13,19,21 AT-25.
- **Fixture/action:** F-OPS approved environment backup contains two tenants, sources/media refs, approvals, schedules, ledger, queued and uncertain accepted job. Restore DB and object recovery into isolated target using runbook; bring API/workers up, verify ownership/lineage and reconcile known remote intent without reposting.
- **Expected persisted state:** Record counts/hashes/tenant isolation/immutable decisions and accessible object hashes match recovery point. No orphan media/approval references; current schema compatible; queued work resumes safely, uncertain work RECONCILING with retained reservation and no duplicate submit. Measure data-loss interval <=24h and total restore-to-usable <=8h under proposed R1 objectives, or record failure/approved target change.
- **Evidence:** `docs/evidence/m6/AT-25/<run-id>/restore-report.json`, backup/restore timestamps, commands, object manifest, DB assertions and job/ledger traces. **Gate:** L rehearsal + V/H deployment-representative authorized drill G-OPS. Initializing empty PG or restoring DB without objects does not pass.

### AT-26 — Workspace deletion and exceptions
- **Status:** NOT RUN. **Milestones/tickets:** M6-02/04. **v6:** §§7,13,16,19,23,21 AT-26.
- **Fixture/action:** F-OPS disposable workspace with private originals/proxies/archive, memberships, scheduled and in-flight provider work, live-publication references and backups. Owner reauthenticates and requests deletion; non-owner attempt must fail. Advance retention clock locally; inspect actual purge/exceptions tracking.
- **Expected persisted state:** Tombstone immediately blocks new work/dispatch/access URL issuance; queued work stopped. In-flight known outcomes may reconcile actual debt/history without authorizing new work. Active-store purge progress targets 7d; backup expiry target 35d, provider deletion capability/exceptions and retained minimized audit/usage visible, not falsely marked deleted. Other tenant unchanged.
- **Evidence:** `docs/evidence/m6/AT-26/<run-id>/deletion-lifecycle.json`, authority/tombstone/queue traces, object checks, purge tracker and provider/backup exception records. **Gate:** L disposable simulation of long retention intervals + V/H approved operational purge/recovery policy G-OPS. Simulated time proves scheduling logic, not actual elapsed retention compliance.

### AT-27 — Unavailable production provider fails visibly
- **Status:** NOT RUN. **Milestones/tickets:** M1-03; M2-03, M3-01, M4-02, M5 adapters, M6-04. **v6:** §§1,3–4,13,15.1,22,21 AT-27.
- **Fixture/action:** F-JOBS production-mode adapter with no config/unimplemented capability, then verified outage/rate-limit variants for AI/transcription/avatar/assembly/storage/social. Include explicit development simulation mode as separate control. Inspect UI job/error and attempt accounting.
- **Expected persisted state:** Typed blocked/retryable/permanent error as appropriate and actionable reason; no automatically generated simulated URL/media/PUBLISHED outcome and no LIVE settlement from fixtures. Safe retries obey limits/backoff/caps; uncertain acceptance reconciles rather than retrying. Development simulation is opt-in, labeled and excluded from real totals.
- **Evidence:** `docs/evidence/m1/AT-27/<run-id>/mode-failure-grid.json`, per-adapter traces/output absence/ledger assertions through M5. **Gate:** L production-mode failure injection + V integration behavior where authorized; deliberate paid outage experiment unnecessary without authority.

### AT-28 — Idempotency key reused with changed request
- **Status:** NOT RUN. **Milestones/tickets:** M1-03/04, M2-02, M5-02; M6-04. **v6:** §§8.1,13–16,21 AT-28.
- **Fixture/action:** F-TENANT/F-JOBS submit paid plan/render/export and publishing mutations with key K; repeat identical request concurrently and after response, then change input versions/account/metadata/body using K in same actor/workspace/operation. Exercise different scoped actor/workspace and stale ETag separately.
- **Expected persisted state:** Same normalized hash replays original response/logical identity; different request returns 409 IDEMPOTENCY_CONFLICT with no second job/attempt/reservation/post. Scoped independent operation does not leak original response. Paid/publication identities survive ordinary seven-day replay cache retention; changing ETag cannot manufacture duplicate side effects. Current-pointer stale edits separately conflict.
- **Evidence:** `docs/evidence/m1/AT-28/<run-id>/replay-grid.json`, normalized hashes, response/unique-key and provider-call counts; M5 publication repetitions. **Gate:** L PG; provider-level dedupe not inferred from internal idempotency (AT-06/14 cover external ambiguity).

### AT-29 — Hard zero paid budget
- **Status:** NOT RUN. **Milestones/tickets:** M1-04, M4-01; M6-04 full paid-operation grid. **v6:** §§13,14,16,23,21 AT-29.
- **Fixture/action:** F-JOBS set workspace cap=0 with positive campaign/job/plan/default config, then zero at each other applicable cap and missing/unconfigured cap. Attempt AI/retrieval if paid, transcription, avatar, assembly, licensed media and billable retry/repair with LIVE-mode outbound spies; separately run permitted nonbillable draft/read/export controls.
- **Expected persisted state:** All paid dispatches blocked BUDGET_EXCEEDED before outbound call; no positive fallback allowance, provider intent sent or LIVE charge. Rejected request/audit/notification may persist, no spend authorization invented. Each accepted paid schema-repair operation would need its own reserve under same approved cap, not free retry. Free independent actions remain available subject to entitlement.
- **Evidence:** `docs/evidence/m1/AT-29/<run-id>/zero-cap-grid.json`, budget/request/attempt/ledger snapshots and zero outbound-call counters; complete adapter grid M6. **Gate:** L; legacy spending-limit test is not this suite and positive live spend is not needed to prove blocking.

### AT-30 — Source prompt injection cannot grant authority
- **Status:** NOT RUN. **Milestones/tickets:** M1-02/05, M2-01/03, M6-04. **v6:** §§7,10,16,19,22,21 AT-30.
- **Fixture/action:** F-TEXT includes instructions inside PDF/DOCX/article/transcript/provider response to reveal a canary secret, fetch internal/exfiltration URL, change brand grants/budget, ignore legal review or publish. Run extraction/retrieval/package/generation/export and render HTML preview with script/markup payloads. Use isolated controlled sinks, never real secrets.
- **Expected persisted state:** Content remains untrusted source data; no tool permission expansion, canary disclosure, unauthorized egress, membership/budget/approval mutation or publication intent. Generated output validates claim schema; unsafe HTML sanitized, source macros/scripts never execute. Any failure is typed/audited without exposing secrets. Legitimate source lineage remains scoped.
- **Evidence:** `docs/evidence/m2/AT-30/<run-id>/injection-security-grid.json`, permission/ledger/publication row diffs, controlled network/tool-call log and sanitized DOM assertions. **Gate:** L adversarial suite plus real model pipeline validation under G-PRODUCTION/G-BUDGET; no malicious source command is treated as authority.

## 4. Supplemental gates (required; not substitutes for ATs)

### SG-MIG — Preservation, immutable schema and PostgreSQL correctness
**Status: NOT RUN. Milestone M1; tickets M1-01/02/03/04; v6 §§3,4,7–9,13–14,19.**

Use empty PG and dirty legacy fixtures with existing media/video records, simulated apparent publications, unknown owner identities and cross-tenant/bad IDs. Apply additive migrations; verify count/hash/ID mapping and no automatic email-only ownership claim. Test total subtype registry integrity, seal/child immutability, same-owner current pointers, typed composite FK failure, concurrent DAG cycles, RLS runtime role and pooled context reset. Exact approval subjects and archive/clip/media references must be enforced, not merely JSON-shaped. Remove automatic destructive schema startup. Rehearse rollback/roll-forward preserving new records or document safe forward-only recovery. Artifact: `docs/evidence/m1/SG-MIG/<run-id>/migration-report.json` plus command/SQL assertions; L PG only. `create_all` success is insufficient.

### SG-EDITORIAL — Approved ten-source set and 1–5 rubric
**Status: NOT RUN. Approval is an M2 gate (M2-04), full evaluated set M6 (M6-04); v6 §§2.2,10–12,21,23.**

Before M2 closes, Martin/brand reviewers supply or approve **at least 10 permitted representative sources** spanning idea, document, human recording and avatar script and **both pilot brands**. Proposed allocation for owner decision, not assumed approval: 2 ideas, 3 documents, 3 recordings, 2 avatar scripts; each brand appears in multiple types. Every fixture needs source hash/version, rights/consent, intended audience/jurisdiction where relevant, expected factual anchors and reviewer identity/approval. Generic development fixtures do not satisfy this gate.

Score exact outputs in five dimensions, with explicit anchors to approve before evaluation:

| Dimension | 1 | 3 | 5 |
|---|---|---|---|
| Factual alignment | Material invented/contradictory claim or changed meaning | Mostly supported, substantive correction needed | All substantive claims/qualifiers accurately supported, locators usable |
| Brand voice | Conflicts with profile/policy | Recognizable voice but meaningful revision needed | Consistently matches approved voice, pronunciation and policy |
| Format suitability | Missing required structure/unusable channel fit | Required structure present, substantial adaptation remains | Native format, appropriate depth/CTA, no transcript truncation shortcut |
| Clip coherence | Misleading cut or unintelligible/out-of-context moment | Understandable with awkward boundary/crop or weak payoff | Self-contained hook/payoff; qualifying language and essential visuals retained |
| Edit burden | Rewrite/rebuild required | Substantive revision required | Ready after only minor copy/cosmetic edits |

Scores 2/4 represent intermediate quality between adjacent anchors; 4 means usable with limited noncritical correction. Capture actual edit minutes and reviewer notes alongside edit-burden score. **Proposed pass, requiring owner approval:** each dimension average >=4, no source below 3, zero critical factual/rights failures. Operationalize “no source below 3” conservatively as no applicable dimension score <3 for any source unless owner approves another explicit interpretation before scoring. Never average away critical failures. Reviewers define critical failure examples (invented legal assertion/evidence, misleading qualifier cut, unlicensed media or unauthorized avatar/voice) and remediation/retest policy.

At M2 approve the entire fixture set/rubric and score applicable text outputs; media/clip scores not yet executable remain **NOT RUN**, not zero or fabricated 4. Any genuinely non-applicable dimension gets a reviewer-approved N/A reason, excluded explicitly from its denominator; clip dimension must still have representative real human/avatar samples. Complete all required dimensions in M3/M4/M6, retaining failures/revision lineage and rescoring corrected exact versions. Artifact: `docs/evidence/m2/SG-EDITORIAL/<run-id>/fixture-approvals.json`, `rubric.md`, `scores.csv`; final M6 report with per-dimension counts/means, per-source minima, critical-failure count and signed verdict. **H + V real outputs required.**

### SG-PERF — Pilot load, queue and schedule timing
**Status: NOT RUN. M6-03; v6 §§14,19.**

Document dataset size and generator seed, workspaces/brands/assets/jobs/publications/object distribution, hardware/DB/storage/worker topology, indexes/versions, warm/cold behavior, load duration and sample counts. Test **20 concurrent interactive users across two workspaces** at documented pilot sizing (defaults 10 users/workspace, 5 brands/workspace, 100GB storage entitlement and 2 paid concurrent jobs/workspace; actual fixture volume must be stated, not claimed to fill 100GB automatically).

Expected measurements under normal operation: **p95 ordinary API reads <=1s; p95 job acknowledgements <=2s**, excluding upload/provider processing; runnable jobs normally claimed **within 30s**; scheduled dispatch starts **within 60s** of target. Record per-route distribution, queue timestamp histogram, dispatch lateness, error rate, tenant fairness and exceeded cases; agree precise statistical interpretation of “normally” with owner before formal pass, do not silently apply p95 to it. Report workload saturation separately. Media completion benchmarks by duration/provider give measured estimates, **no invented render SLA**. Keep external posting disabled or use explicitly authorized tests; local controlled sink measures scheduler start, not successful remote publication. Artifact: `docs/evidence/m6/SG-PERF/<run-id>/performance.json` and raw redacted measurements. L + V deployment-representative environment/H workload agreement.

### SG-UX — Workflow, editing and accessibility
**Status: NOT RUN. Incremental M2–M5, final M6-04; v6 §§5.1–5.6,6.2,12.1,17.**

Use actual assets and granted roles through Home/Create/Content Library/Review/Calendar/Analytics/Brands/Settings with always-visible workspace switch. Execute source→strategy→package review→plan/estimate→production/review→schedule/download; save/resume text-only without avatar; partial-success retry/review/download; claim excerpt/diff/scene-time comments; scene order/narration/media replacement/caption style/trims/crop/template/preview and cost warning. Verify list/week timezone calendar, destination filter, move-to-pending approval, no fabricated percentage and actionable failures. Keyboard-only operation, focus order, labeled controls, contrast and caption controls reviewed; log actual defects and retest. Artifact: `docs/evidence/m6/SG-UX/<run-id>/workflow-accessibility.json` with UI traces/video and persisted decision IDs, not empty-screen screenshots. L + H; frontend dependency/build block must first resolve G-ENV.

### SG-UAT — Both teams, not a single demonstration workspace
**Status: NOT RUN. M6-04; v6 §§2.1–2.3,5,7,20,24.**

Authorized **AI Marketing Box and Tailor Law users each** complete self-service core journey in their own isolated workspace: onboarding/brand; topic/document; human recording and avatar route; real written portfolio/main video; selected 3–5 viable moments/four short-form profiles; editing/exact reviews; five direct destinations; useful downloads; native metrics/actual usage/blockers. Record a team-by-workflow matrix, actor roles/grants, version/approval/run IDs, defects and explicit team sign-off. Tailor Law has actual designated reviewer and jurisdiction/substantive legal review; generation approval never equals publication authorization. Owner must resolve authorized accounts/access for each team's required workflow; no hidden substitution with another team's account. Fixture-approved shortfall is explicit, not fabricated clips. Artifact: `docs/evidence/m6/SG-UAT/<run-id>/team-workflow-grid.json` plus sign-offs. H + V; one team's success cannot close the other team's row.

### SG-CI — Reproducible, safe build and runtime contract conformance
**Status: NOT RUN for complete gate; M0 partial logs only. M1-05 and M6-03; v6 §§4,16,19,22.**

Clean install from pinned lockfiles, deterministic schema/event generation and independent validation, backend unit/integration, actual FastAPI response/policy conformance, PG migration/constraint tests and frontend production build must pass in safe CI. Verify API schemas committed before matching UI and target contract is not falsely served as deployed implementation. Tests cannot drop/reset production DB; missing positive disposable-DB marker denies destructive execution. Record commands, commit, dependency versions and logs at `docs/evidence/m6/SG-CI/<run-id>/ci-manifest.json`. L; existing E403 is G-ENV blocked, not test success or permission to evade controls.

### SG-OPS — Recovery, retention, privacy and operator handoff
**Status: NOT RUN. M6-02/03/04; v6 §§4,13–16,19,22–23.**

AT-25 restore and AT-26 deletion must pass with approved operational settings. Runbook specifies daily DB backups/object recovery, <=24h data loss/<=8h restore demonstration, schema rollout/rollback, separate workers, secret rotation/redaction, lease/queue/uncertain-provider/cost alerts, operator reconciliation authority, incident escalation and connector revocation/takedown limitations. Validate private original/output storage, default ten-minute signed access and justified longer purpose-limited provider retrieval, seven-day archive expiry, 30-day inactive proxy cleanup, 12-month minimized audit/usage, seven-day active-store purge and 35-day backup expiry targets; these are proposed defaults requiring owner disposition before destructive production behavior. Persist exception/approval and measured results rather than asserting legal compliance. Artifact: `docs/evidence/m6/SG-OPS/<run-id>/operational-readiness.json` and reviewed DEPLOYMENT/runbook references. L + V/H G-OPS; no production purge/deployment authorized by this matrix.

## 5. Milestone verdict checklist

| Milestone | Required acceptance package | Current verdict |
|---|---|---|
| M0 | Baseline/commit/schema/config/test inventory; reproducibility; architecture/contracts/provider-account gates; this matrix/backlog reviewed. | **PARTIAL / NOT ACCEPTED**. SQLite legacy 3 pass and PG16.2 legacy initialization are limited observations; frontend E403/build unresolved. |
| M1 | AT-01/02/05/06/07/08/09/10/20/27/28/29/30 applicable foundation cases, SG-MIG/CI, identity/private storage integration. Later-media/provider stages still open. | **NOT RUN** for v6 gate. |
| M2 | AT-03/04/09/10/12/20/24/27/28/30 text cases; **approved >=10-source fixtures/rubric** and real-provider reviewed text outputs. | **NOT RUN**; G-EDITORIAL/G-PRODUCTION/G-BUDGET need evidence. |
| M3 | AT-11/19/20/21-human/22/24 media cases and human editorial acceptance. | **NOT RUN**. |
| M4 | AT-06/08/09/10/13/19/21-both/22/24/27/29 avatar/assembly cases, consent and real usage reconciliation. | **NOT RUN**. |
| M5 | AT-04/13/14/15/16/17/22/23/27/28 integrated scheduling/accounts, per-destination authorized publication and supported metrics. | **NOT RUN**; access/publication authority not assumed. |
| M6 | Every AT-01–AT-30 and SG-MIG/EDITORIAL/PERF/UX/UAT/CI/OPS; both-team sign-off, recovery/deletion/native metrics/conversions. | **NOT RUN / R1 NOT ACCEPTED**. |
| M7 | Separately approved R2 commercial spec and new subscriber suite plus unchanged R1 regression. | **GATED / NOT RUN**; no R2 acceptance inferred from AT-01–AT-30. |

Final review requires a retrievable evidence bundle for every verdict. An explicit owner-approved scope change is recorded separately with changed requirement and residual risk; it is not a fabricated PASS. An inaccessible provider, missing account scope, unapproved fixture, unresolved UI build or unexecuted recovery drill remains a blocker. Acceptance does not itself authorize spending, posts, merging or deployment.
