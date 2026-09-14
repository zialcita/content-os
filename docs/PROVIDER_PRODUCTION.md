# Content OS — provider production architecture, M0 research

**Research date: 2026-09-11 UTC. Status: proposal, not implementation or live proof.**

Scope: retain the existing FastAPI / SQLAlchemy backend and Next.js 15 / React 19 frontend as a modular application. The supplied stack is the architectural baseline; no repository was available in this research workspace, so package-lock compatibility and existing code were not audited. No credentials were configured or verified; no authentication flows, uploads, transcription, avatar generation or renders were executed. No accounts, paid production API calls, webhooks, publications or deployments were created. Public documentation research is the evidence, not proof of account entitlement or service behavior. The owner's live-provider budget is zero.

## 1. Specific engineering decisions

1. **FastAPI owns authentication and authorization.** Prefer Authlib's async Starlette OIDC client, a first-party opaque PostgreSQL-backed application session, and self-hosted Keycloak for a no-commercial-signup identity-provider option. Do not build password authentication or JWT signature validation ourselves. Keep Next.js a same-origin UI/BFF proxy, not a second independent identity/session authority.
2. **Private object storage behind an S3-compatible adapter.** Implement resumable S3 multipart direct-browser uploads, with quarantine and authoritative server completion. AWS S3 and Cloudflare R2 remain deployment choices; recommend R2 Standard conditionally for delivery economics, not as a claim that an account exists or is free to operate. A 2 GB application limit is far below either service's multipart limit.
3. **PostgreSQL durable workers, not microservices or in-process background tasks.** API and workers share modules, schema and versioned deployment artifact, with separate process roles. Use transactional outbox/job rows, leased claims and idempotent transitions. Do not add Redis/Celery merely to obtain a queue.
4. **Versioned capability adapters:** StructuredAI, Transcriber, AvatarProvider, AssemblyProvider, ObjectStore and MediaValidator. Start with deterministic fake adapters; all external execution defaults to disabled.
5. **HeyGen is the first avatar adapter candidate.** Research currently points to v3, not a copied v2 payload. Pin engine and endpoint contract; owner must approve a stock avatar, voice, account, processing rights and bounded spend before any live request. Custom likeness/voice cloning is not part of M0.
6. **Shotstack is the first cloud-assembly candidate, not an approved provider.** Use a provider-neutral edit decision list (EDL) that can also compile to local FFmpeg. FFmpeg/ffprobe validates all ingest and output media. Local fixtures can demonstrate mechanics without a paid API.
7. **Time-coded transcription:** Deepgram pre-recorded is the primary future candidate when word timestamps plus diarization matter; OpenAI whisper-1 is a viable word/segment-timestamp fallback. Do not assume every newer transcription model has word timestamps. No automatic provider failover that spends money.
8. **Structured AI:** OpenAI schema-constrained responses is the first candidate; Gemini schema-constrained output is an alternative. Validate both syntax and domain semantics with Pydantic. A model never directly authorizes publishing, spending or arbitrary source URLs.

These are engineering recommendations for later implementation, not owner approvals or completed integrations.

## 2. OIDC and session options without commercial signup

### Recommended: Authlib + self-hosted Keycloak + app sessions

Authlib's official async Starlette integration supports OIDC discovery, authorization-code exchange and ID-token parsing [A1]. Its official releases show continuing 1.6/1.7-series maintenance and security-related changes [A2]; pin an exact supported release only after checking the existing Python/FastAPI/Starlette/HTTPX dependency graph. Keycloak provides discovery, authorization/token/JWKS/userinfo/logout/revocation endpoints, container deployment guides and active releases [A3–A5]. Self-hosting does not require a hosted commercial identity signup, but production operation still needs approved hosting, TLS, backups, patching and an operator.

Proposed flow: `/auth/login` creates a short-lived, single-use server-side OIDC transaction containing state, nonce, PKCE verifier and allowlisted return path. Use authorization code + PKCE S256 with a confidential client. `/auth/callback` validates state/nonce/issuer/audience/expiry and exchanges the code via the library; allowlisted issuer and discovery URL are configuration, never supplied by a user. Associate identity with `(issuer, subject)`, not mutable email. Rotate the application session at login/privilege change. Store only a cryptographically random opaque handle in a Secure, HttpOnly, SameSite=Lax, host-only cookie (prefer `__Host-`); store its digest and session expiry/revocation in PostgreSQL. Encrypt provider tokens server-side if retained, minimize scopes and avoid offline refresh unless required. Local logout revokes the app session immediately; provider RP logout is additional, not a substitute. If provider-wide logout must invalidate existing app sessions, implement/test backchannel logout or short reauthentication explicitly.

**Do not mistake a signed cookie for encrypted storage.** Starlette SessionMiddleware documents that session information is readable, though tamper-protected [A6]. Do not place access/refresh tokens or sensitive user data there. Use maintained protocol primitives while keeping the app's small revocable session lifecycle in its existing SQLAlchemy model layer. CSRF token and Origin checks protect state-changing cookie-authenticated routes; SameSite alone is not enough. Enforce authorization/workspace membership in every backend query, including uploads and callbacks. Never trust frontend role checks.

### Alternatives and trade-offs

- **Self-hosted authentik** is an OIDC-provider alternative supporting PKCE, discovery, refresh rotation and scope mappings [A7]. Prefer it if already operated by the owner; otherwise avoid running two identity systems. Its issuer and signing-key settings must be explicit; the docs distinguish asymmetric signing from client-secret signing. Production sizing/version/security review remains open.
- **Auth.js + Keycloak** offers a maintained ecosystem with a documented Keycloak provider and JWT or database-session choices [A8–A9]. Database sessions provide server-side invalidation. It is an architectural alternative if Next.js is made the sole BFF/auth authority, not an additional session layer on top of FastAPI. It introduces an authenticated trust boundary to FastAPI and requires specific Next 15/React 19 version verification; not selected here. Auth.js release compatibility was not proven in this research.
- No hosted Auth0/Clerk/Cognito signup is required for the selected local path. No claim that self-hosting is operationally free. Do not use a DIY credential table as the shortcut.

## 3. Private 2 GB resumable uploads and quarantine

**Proposed product definition:** `max_upload_bytes = 2_000_000_000` (decimal 2 GB); if the owner intends 2 GiB, make that an explicit policy change. Choose 16 MiB fixed parts, except final part: at most 120 parts for the decimal cap (128 at 2 GiB). Four concurrent browser PUTs is a conservative starting policy, not a provider quota.

R2 multipart supports 5 MiB minimum parts (last excepted), 5 GiB maximum parts, 10,000 parts and equal non-final part sizes [S1]. Its limits page distinguishes nominal object capacity from multipart overhead [S2]; neither affects our 2 GB policy. S3 multipart can retry individual parts and remains allocated until completed/aborted, with storage charges for unfinished parts [S5]. R2's unsupported presigned **POST HTML form upload** is not a prohibition on S3 multipart UploadPart PUT requests [S3]. Presigned URLs are bearer capabilities, not public-bucket configuration.

### Protocol and controls

1. Authenticated `initiate`: validate workspace, accepted media class, declared bytes and reserved quota; generate immutable random object key under a private quarantine bucket/prefix. Record upload ID, owner, expected bytes, part size/count, expires_at and state in PostgreSQL. Keep original filename as sanitized metadata only.
2. Backend uses least-privileged server storage credentials for initiate/list/complete/abort; browser receives short-lived UploadPart URLs only for authorized upload IDs and allowed part numbers, issued in a bounded window. Never proxy 2 GB through Next.js, FastAPI, a Worker, a request buffer or a base64 JSON payload.
3. Browser slices the file without whole-file buffering and persists a resumable upload handle locally. Resume checks backend ListParts and stored state; renew expired part URLs after auth. Part ETags are completion tokens, **not a dependable whole-file MD5**. Restarting a part number safely replaces that part, but completion and immutable finalized keys require separate locking.
4. CORS allows exact frontend origins, PUT and required signed headers; expose ETag [S4]. CORS is not access control. Never log signed URLs. R2 presigned URLs use its S3 API endpoint; do not assume custom-domain URL signatures work.
5. Backend alone completes, under a state transition lock, after authoritative part-count/size validation; enforce expected total and policy cap. HEAD the completed object; independently stream/hash and validate actual type/duration. Reject unexpected parts/oversize and delete/abort invalid data. Presigning is not a universal hard byte-range enforcement mechanism: test signed Content-Length/checksum support per provider, reserve quota, limit issuance and sweep abusive/orphan uploads. A malicious client may still upload temporary oversized parts before validation; document and bound that exposure rather than claiming it is impossible.
6. State machine: `initiated → uploading → uploaded_quarantined → scanning → ready | rejected`; `aborted/expired` are terminal. No preview, download-to-provider, transcription or rendering from quarantine.
7. Worker performs MIME magic/container verification, malware scanning appropriate to policy, ffprobe + bounded decode, duration/stream/resolution limits and checksum; a missing scanner is a failed gate, not a pass. Run parsers non-root, without network, with CPU/memory/time/disk limits and patched tools. Reject unsupported/encrypted/corrupt files and malicious playlist/network references. Store normalized derivatives separately, retaining provenance and source checksum.
8. Promote only validated bytes to an immutable clean key (storage copy is not assumed atomic with SQL). Use an idempotent promotion job and commit `ready` only after destination verification. Lifecycle/worker sweeps abort incomplete uploads and remove orphan/rejected objects; reconcile DB and storage states.

Keep buckets private: no `r2.dev`, public custom-domain hosting, public ACL or public list access. Later owner-approved provider ingestion may receive scoped, expiring HTTPS GET capabilities to *clean derivatives*, valid through expected queue/fetch/retry time. This deliberately grants temporary third-party read access, not publication. Provider acceptance of signed query URLs and expiry behavior require live proof. Do not extend access indefinitely after a job stalls. R2/S3 encryption features and jurisdiction must be approved per actual account; do not assume identical SSE/KMS support.

## 4. AI and transcript adapter contracts

### Structured AI

`generate(schema_version, source_refs, prompt_version, model_pin, policy) → ValidatedResult | Refusal | Incomplete | ProviderError`.

Use a supported JSON Schema subset and server-owned schemas through the selected provider's structured-output API [I1–I2]. Capability depends on exact model and endpoint; docs evolve, including Gemini Interactions APIs, so do not copy a schema into an unrelated endpoint. Strict output constrains shape, not truth. Pydantic/domain validation must enforce clip intervals within source duration, stable asset IDs, caption lengths, output enum choices, bounded list sizes and no external URLs/code. Keep factual claims linked to source transcript spans; refusal/truncation/schema mismatch are explicit states. Treat source documents/transcripts as untrusted data. Only validated plans can be reviewed/compiled; never execute model-provided shell filters.

API credentials stay server-side. OpenAI uses bearer authentication; Gemini credential wiring and chosen endpoint must be confirmed from the pinned API contract before implementation. M0 uses fixtures and no callback. A worker timeout is not evidence a paid request was not processed; record ambiguous outcomes and avoid unbounded retry/repair loops. Log input/output usage and model/version when reported, but redact prompts and secrets according to retention policy.

### Time-coded transcription

Canonical transcript: source checksum, provider/model/version, language, source duration, segments `{start_ms,end_ms,text,speaker?}`, optional words `{start_ms,end_ms,text,confidence?}`, timestamp quality/granularity, chunk provenance and review status. Use integer milliseconds internally and explicit seconds conversion at adapter boundaries. Diarization labels are not verified real-person identities.

- **Deepgram pre-recorded** [T1–T3]: POST `/v1/listen`, `Authorization: Token ...`, binary audio or URL; results include word start/end/confidence and optional speaker labels/utterances. Current reference describes `diarize_model` and deprecates the older boolean `diarize`; pin the selected model rather than use `latest`. Guide states 2 GB maximum input and processing-time timeouts of 10 minutes for Nova/Base/Enhanced and 20 for Whisper; these are processing timeouts, not guaranteed maximum audio durations. Extract normalized audio from large video instead of forwarding the original 2 GB object. Callback mode immediately returns `request_id`. Callbacks retry up to ten times after non-2xx responses, at 30-second delays. Docs offer Basic Auth and `dg-token` containing the API-key identifier; **that identifier is not an HMAC or secret equivalent to the API key**. Prefer a separately generated callback credential over TLS, redact credentials from URLs/logs, correlate request ID and validate payload bounds. Durable-store callback before 2xx. Deepgram says transcripts are not stored for later retrieval: losing the result is not necessarily recoverable by polling; do not promise that path.
- **OpenAI file transcription** [T4–T5]: bearer auth; guide states 25 MB input cap. `whisper-1` supports verbose JSON with word/segment timestamps and SRT/VTT. `gpt-4o-transcribe-diarize` supports speaker segments via `diarized_json`, requires chunking strategy beyond 30 seconds and does not support `timestamp_granularities[]`; it is not a drop-in word-timing source. Other model defaults are moving; capability-check rather than assuming a newer model preserves features. Standard file request runs in a durable worker; no generic transcription completion webhook assumed.

Split audio to provider limits with overlap/VAD, preserve global offsets and deduplicate overlap; test words around chunk boundaries. Preserve separate channels where useful. Reject non-monotonic/out-of-bounds timestamps. Timing is estimated, not frame-perfect truth. Recompute caption timing against generated avatar audio or reliable provider subtitles; original-source transcript timing is not transferable to newly spoken scripts. A fixture adapter is the zero-provider-budget route; local STT would require separate model-license/download/resource review and was not installed here.

## 5. HeyGen first avatar provider — current v3 contract and caveats

Current official documentation exposes `POST /v3/videos` and `GET /v3/videos/{video_id}` [H1–H4], unlike legacy v2 guides. Use explicit `type: avatar`, discovered avatar/voice IDs, an explicit engine and exactly one speech source: script or audio. Do not invent IDs or silently use a premium default. Engine eligibility varies by avatar; photo-avatar expressiveness/motion, digital-twin features and alpha/matting are conditional. M0 recommendation: stock licensed avatar, ordinary MP4, 720p or 1080p, no custom cloning, no cinematic/video-agent generation. Let assembly own final captions.

**Limits:** fresh usage-limits page states 5,000 script characters, 600-second audio input, 25 fps avatar output, 50 scenes maximum and **30 minutes per scene**. Single-scene avatar/image calls therefore cap at 30 minutes; multi-scene total is described as the sum of allowed scenes. An older cached excerpt summarized this as a 30-minute whole-video cap; prefer the fresh page but do not turn its theoretical multi-scene limit into a product guarantee. Fresh resource limits: video MP4/WebM 100 MB and <2K, images JPG/PNG 50 MB and <2K, audio WAV/MP3 50 MB; ordinary `/v3/assets` uploads max 32 MB, with a separate direct-upload flow returning `max_bytes`. A 2 GB accepted Content OS source is not a valid HeyGen input as-is. Aspect-ratio guide lists more ratios than general limits page; approve only 16:9/9:16 pending contract proof. Script speech duration is not an exact controllable target; probe actual generated media before assembly. Proposed initial product clip cap is 60 seconds, not a documented provider cap.

**Authentication:** `X-Api-Key` for direct API; current docs also mention OAuth bearer access [H3]. Use direct API credentials only after owner setup. Do not equate an existing web subscription or MCP credit pool with API wallet entitlement [H5].

**Submission idempotency:** current create-video schema documents optional `Idempotency-Key`, 24-hour replay window, and `409 request_in_progress` while the original is in flight. Keys are endpoint/resource scoped. The docs say slightly changed payloads may replay the original response: enforce an immutable payload hash locally; never reuse a key for a revised script. Persist intent/key before sending. After the replay window or uncertain account behavior, hold ambiguous submissions for reconciliation; do not create another paid video automatically. This is v3 documentation evidence, not verified account behavior or a guarantee for v2.

**Callbacks:** managed v3 webhooks return a one-time signing secret; cached detailed docs specify HMAC-SHA256 over raw body, `Heygen-Signature`, `Heygen-Timestamp`, `Heygen-Event-Id`, 2xx within 10 seconds and retries up to 24 hours [H3]. Verify raw bytes in constant time; durable-dedup the event and semantic `(provider_job_id,event_type,status)` transition. Timestamp alone is insufficient because the documented signature covers the body, not that header. Header semantics/retry-ID stability must be frozen from a full contract snapshot and fixture-tested before live use. Bare per-request callback URLs are not assumed to have identical signatures; if unverifiable, treat as a hint and authenticate a status fetch. Rotate secrets deliberately: docs say old secret invalidates immediately.

**Output:** download completed `video_url` promptly into private quarantine/validation. Sidecar and burn-in outputs are separate and guide/schema wording about whether subtitles are always returned differs; request explicitly and handle absent fields. Output URLs expire; authenticated status fetch can refresh URLs according to the guide. Store own clean durable result, not expiring provider links. No render-latency SLA inferred from examples.

## 6. Shotstack assembly candidate and FFmpeg validation

Shotstack Edit API [V1] accepts a timeline with ordered tracks/clips/assets and output parameters via `POST https://api.shotstack.io/edit/{stage|v1}/render`, authenticated with `x-api-key`; persist render ID and poll `/render/{id}` as reconciliation. Current reference outranks older tutorials with mixed URL paths.

| Need | Proposed EDL → assembly mapping | Limitation / validation |
|---|---|---|
| Trim | source `in_ms` → video asset `trim`; clip `start` is timeline time; `length` is visible duration | These are different clocks; validate against actual probed source; re-encode for frame-accurate FFmpeg cuts. |
| Crop/reframe | explicit crop + fit/scale/position/offset; final aspect ratio in output | Not automatic subject tracking. Face-safe composition requires reviewed framing/keyframes, not an assumed AI feature. |
| B-roll | licensed image/video assets on higher visual tracks with explicit durations | Assembly does not source licensed B-roll by itself. Mute B-roll audio unless selected; retain asset rights/provenance. |
| Captions | caption/rich-caption asset or controlled text clips from canonical cues; export SRT/VTT sidecars | Verify exact supported subtitle format/style at pinned contract; prevent double burn-in. Word animation requires real word timing. |
| Mix/transitions | soundtrack/audio/video volume, fades, overlays and explicit transitions | Review clipping, intelligibility, gap/overlap and timing; effects change compute time. |

Sources must be HTTPS-fetchable by Shotstack: use approved temporary clean-object capabilities, not public buckets. Default Shotstack hosting can create a separate served copy; explicitly configure `output.destinations` to exclude Shotstack hosting (schema example supports `provider: shotstack, exclude: true`) and validate privacy before live testing. Temporary output still exists on provider infrastructure; privacy/retention approval is mandatory. Do not use Serve/CDN as the app's canonical private store. Official guide says Edit temporary output expires after 24 hours [V3]. Download and validate promptly.

**Callback security:** official documentation explicitly says callbacks are not signed [V2]. POST body is an untrusted notification only. Accept only known render IDs, bounded schemas, rate-limited ingress; enqueue an authenticated GET to verify job ownership/status/output URL. Never mark a result ready or fetch arbitrary callback URLs directly. Respond quickly after durable enqueue; docs specify ten-second timeout and retries for response codes outside 200–399, up to ten requeues with exponential backoff. No Shotstack render-submit idempotency guarantee was established in reviewed docs: a network timeout after POST yields `submission_unknown`; do not blindly resubmit and incur another render.

**Limits/cost boundary:** docs state source files up to 5 GB and combined sources/output up to 10 GB [V4]. Sandbox is watermarked, capped at ten minutes and requires at least one credit. Ordinary sandbox edits may not consume credits, but AI-generated assets can be chargeable even there [V5]. No sandbox call is authorized under the zero-live-budget rule. A production maximum duration or guaranteed latency was not conclusively established; file capacity and plan limits still apply. Product duration should remain conservative until proven, rather than promising arbitrarily long timelines.

**Local FFmpeg:** compile the same restricted EDL to `trim/atrim`, `setpts/asetpts`, `scale/crop/pad`, `overlay`, `concat`, audio mix and `subtitles`/ASS where build support exists [F1]. Check filter/codec availability and FFmpeg build/license (libass and chosen codec licensing are not universally identical). Inputs are local validated files; never concatenate user strings into a shell/filtergraph. Use argument arrays and constrained filter generation. Sandbox FFmpeg and bound resources.

Validation gates [F2]: ffprobe JSON for actual container/streams/duration/dimensions/SAR/DAR/fps/rotation/audio channels; decode full output with bounded FFmpeg error checking. Validate expected streams, final aspect, missing audio, truncated output and total duration to a defined frame/audio tolerance. Check cue intervals, captions after trim/cut, dropped/duplicated cues, Unicode/font glyphs and frame samples across transitions; human review for legibility/crop/lip-sync. Audio silence/black-frame detection is a warning requiring context, not proof of failure. A successful ffprobe alone does not prove a playable complete file. Preserve checksums and validation manifest. No local FFmpeg proof was run in M0.

## 7. Durable worker architecture and uncertainty

Suggested SQLAlchemy-owned tables: `identity_links`, `app_sessions`, `oidc_transactions`, `upload_sessions`, `assets`, `asset_versions`, `jobs`, `job_attempts`, `provider_requests`, `webhook_inbox`, `outbox`, `transcripts`, `edit_plans`, `renders`, `approval_records`, `usage_ledger`. Use existing tenancy/user models rather than duplicating them; names are proposals pending repository inspection.

A transaction writes business state plus outbox/job intent. Workers claim due jobs via `FOR UPDATE SKIP LOCKED` [D1], atomically set lease owner/token/expiry and commit before external I/O. Heartbeat/extend long work; compare lease token on every transition, reclaim expired leases and prevent stale workers overwriting new results. No network calls while holding SQL locks. Bounded attempt counts, jittered retry with Retry-After, dead-letter/manual review and separate provider concurrency semaphores. Worker restart tests must cover claim, before-send, after-send-before-ID, download, promotion and callback race boundaries.

Explicit states: `queued`, `running`, `waiting_provider`, `submission_unknown`, `validating`, `succeeded`, `failed`, `cancel_requested`, `cancelled`. Local cancellation is not evidence of provider cancellation/refund; do not implement a nonexistent cancellation API. Successful output delivery must be repeatable from immutable stored results without rerendering. At-least-once processing, not magical exactly-once execution. Unique local request fingerprint includes tenant, operation, immutable input hashes, provider/model/config and approved plan version. Never auto-switch providers on error.

Webhook handlers validate/authenticate or classify as untrusted hints, insert deduplicated inbox rows, return promptly and let workers process. Out-of-order callbacks must not regress terminal state; polling and callbacks share one transition function. Authenticated polling is bounded and scheduled, not a tight loop. Download destinations resolve only validated expected provider/object-store domains, reject private/link-local/metadata addresses and unsafe redirects, impose byte/time limits and recheck resolved addresses to control SSRF.

**Budget guard:** provider adapters remain `disabled` by default and fail closed even when a secret is present. Enabling needs an owner approval record with provider/model/account, rights/retention terms, exact maximum run count, per-job/total currency cap and expiry. Estimate/reserve before call, reconcile actual usage after; estimates are not exact bills. Unknown spend stays reserved. At budget zero, even “free trial” or sandbox requests remain blocked. Never activate auto-top-up, burst concurrency, paid fallback or retries that can duplicate mutations without approval.

## 8. Costs: informative only, not permission

Storage charges include GB-month, multipart operations/abandoned parts, derivatives and provider copies. R2 Standard public pricing lists $0.015/GB-month, $4.50/million Class A and $0.36/million Class B operations with free direct internet egress; free-tier allowances are not a zero-cost guarantee [C1]. AWS costs are region/operation/egress dependent; no region quote selected. Shotstack pricing advertises PAYG from $0.30/minute and subscription from $0.20/minute, with plan/credit conditions [C2]; calculate actual charged rounding and regeneration costs only after owner reviews current account terms. HeyGen public API page advertises PAYG starting at $5 and distinguishes API-wallet billing from web-plan/MCP credits [H5]; no engine-specific rate or entitlement is guaranteed here. AI/transcription costs depend on pinned model, duration/tokens, optional features and repeats; current account price cards must be captured before approval. FFmpeg/local identity software avoids paid provider calls, but compute/hosting/operations are not free.

**Owner-required decisions:** identity operator/provider/hostname/MFA policy; storage account/region/retention/encryption/quota definition; external processing/DPA and privacy acceptance; avatar/voice/B-roll rights; provider accounts/keys and exact model/engine entitlement; spend caps and any sandbox consent; callback domain/TLS deployment; artifact retention/deletion; production deployment. None were supplied or approved here.

## 9. Proof strategy and exit gates (planned, not executed)

**M0 complete:** dated source review and this architecture proposal only. Evidence labels below are intentionally distinct.

**P0 offline/unit proof after implementation authorization:** deterministic fakes and captured/redacted schema fixtures; test OIDC state replay/wrong issuer/nonce/CSRF/session rotation/expiry/cross-tenant denial; multipart parts/refresh/resume/cancel/cap/quota/quarantine/race tests; transcript offset/granularity tests; schema refusal/truncation/semantic rejection; job lease recovery; spoofed/duplicate/out-of-order callbacks; paid-submit timeout -> unknown, not retry. Golden EDL compilation and generated local colorbar/tone media for trim/crop/B-roll/caption frames and decode. These prove application logic, not vendor integration.

**P1 local integration proof after authorization:** local Keycloak realm + PostgreSQL plus an approved S3-compatible local test server (license reviewed). Browser round-trip session, dropped upload/network/resume across server restart, 2 GB boundary streaming without full memory allocation, malware/corrupt-media isolation and FFmpeg output validation. Local S3 compatibility does not prove R2's CORS, checksum or presigning behavior. No downloads or infrastructure were provisioned in this M0.

**P2 owner-gated live provider proof:** narrowly capped, rights-cleared 5–10-second fixtures; privately signed derivative access, HeyGen exact engine/stock IDs and callback HMAC, output expiry refresh, duplicate submission key behavior; Shotstack signed input fetch and verified unsigned callback, disabled hosting behavior, captions/trim/crop/B-roll render plus FFmpeg/visual validation. Reconcile billed usage and retention/deletion. Verify actual duration/file/plan limits and callback retry semantics from account evidence. A sandbox result is not production entitlement proof.

**Production exit:** explicit approvals, dependency/security review, migrations/rollback, backup restore, durable-worker crash/race proof, private storage/access tests, data retention/third-party deletion, bounded costs, observability with redaction, failed-job repair runbook and output review. “Production ready” cannot be claimed from M0 or a successful isolated render.

## 10. Dated official-source register

All URLs below were reviewed **2026-09-11 UTC**. This is an access/research date, not an invented publication date. Most pages are rolling documentation; search/cache extracts may lag. HeyGen H1/H3/H4 were additionally requested with fresh crawl, exposing documented drift; exact API schemas must be snapshotted before implementation. Failed candidate URLs were not used as evidence. No signed-in/account-specific information was obtained.

### Identity
- A1 Authlib Starlette OIDC: https://docs.authlib.org/en/latest/oauth2/client/web/starlette.html
- A2 Authlib official releases: https://github.com/authlib/authlib/releases
- A3 Keycloak OIDC endpoints/security: https://www.keycloak.org/securing-apps/oidc-layers
- A4 Keycloak operations/deployment: https://www.keycloak.org/guides
- A5 Keycloak releases: https://github.com/keycloak/keycloak/releases
- A6 Starlette signed-cookie sessions: https://www.starlette.io/middleware/
- A7 authentik OAuth/OIDC: https://docs.goauthentik.io/add-secure-apps/providers/oauth2/
- A8 Auth.js Keycloak: https://authjs.dev/getting-started/providers/keycloak
- A9 Auth.js session strategies: https://authjs.dev/concepts/session-strategies

### Storage
- S1 R2 upload/multipart details: https://developers.cloudflare.com/r2/objects/upload-objects/index.md
- S2 R2 platform limits: https://developers.cloudflare.com/r2/platform/limits/
- S3 R2 presigned URL operations: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- S4 R2 CORS: https://developers.cloudflare.com/r2/buckets/cors/
- S5 AWS multipart overview: https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html

### AI/transcription
- I1 OpenAI structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- I2 Gemini structured output: https://ai.google.dev/gemini-api/docs/structured-output
- T1 Deepgram pre-recorded guide/limits: https://developers.deepgram.com/docs/pre-recorded-audio.mdx
- T2 Deepgram API/word timestamp schema: https://developers.deepgram.com/reference/speech-to-text/listen-pre-recorded.mdx
- T3 Deepgram callbacks/auth/retries: https://developers.deepgram.com/docs/callback.mdx
- T4 OpenAI speech-to-text limits/model differences: https://developers.openai.com/api/docs/guides/speech-to-text
- T5 OpenAI transcription reference: https://developers.openai.com/api/reference/resources/audio/subresources/transcriptions/methods/create

### HeyGen
- H1 Current create-video reference/idempotency: https://developers.heygen.com/reference/create-video
- H2 Avatar generation/status/output: https://developers.heygen.com/generate-avatar-video
- H3 Managed webhooks/signatures: https://developers.heygen.com/docs/webhooks
- H4 Fresh input/output/concurrency limits: https://developers.heygen.com/docs/usage-limits
- H5 API billing paths/pricing: https://www.heygen.com/api-pricing
- H6 Version mapping (v2/v3 are not interchangeable): https://developers.heygen.com/endpoint-version-comparison

### Assembly, validation, durability, costs
- V1 Shotstack schema/endpoints/assets: https://shotstack.io/docs/api/
- V2 Shotstack callback/retry/no-signature warning: https://shotstack.io/docs/guide/architecting-an-application/webhooks/
- V3 Shotstack temporary outputs: https://shotstack.io/docs/guide/getting-started/hello-world-using-curl/
- V4 Shotstack limitations/sandbox: https://shotstack.io/docs/guide/architecting-an-application/limitations/
- V5 Shotstack tutorial and sandbox/AI billing caveat (page displays August 5, 2026): https://shotstack.io/learn/render-your-first-video-shotstack-api/
- F1 FFmpeg filters: https://ffmpeg.org/ffmpeg-filters.html
- F2 ffprobe: https://ffmpeg.org/ffprobe.html
- D1 PostgreSQL SKIP LOCKED queue semantics: https://www.postgresql.org/docs/current/sql-select.html
- C1 R2 pricing: https://developers.cloudflare.com/r2/pricing/
- C2 Shotstack pricing: https://shotstack.io/pricing/
