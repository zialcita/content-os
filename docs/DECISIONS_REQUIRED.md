# Decisions and external gates

Date: 2026-09-11. Routine implementation decisions are resolved in ADR0001/0002. This register asks only for facts/authority engineering cannot manufacture. No secret should be pasted into a chat or committed. Existing Hyperagent connections do not establish OAuth authority for the application being built.

| ID | Decision/input | Recommendation or safe default | Needed by / current status |
|---|---|---|---|
| G01 | Allow registry.npmjs.org dependency downloads | Owner reported approval; fresh retry still blocked by network policy. New access request surfaced; keep existing lock and registry | M0 frontend install/build; BLOCKED E403 |
| G02 | Production OIDC issuer/provider and owner-controlled account/project | Owner confirmed no existing identity service. Keep Authlib/configurable OIDC and local Keycloak candidate; production service choice and provisioning remain unapproved | M1 real identity integration; owner selection/account access pending |
| G03 | Hosting project, region and operating cost ceiling | Retain container deployment; separate API/web/worker, managed PostgreSQL, private storage. Existing Render-compatible Dockerfile is not evidence of a deployment | Owner prefers reuse but skipped host/project details; pending before provisioning/deployment. Local backend tests do not wait for this |
| G04 | Legacy data exists? Owner/brand mapping and historical timestamp provenance | Do not connect to a live database yet. Obtain an authorized sanitized inventory/backup; never infer owners by email or keys | M1 actual migration rehearsal/cutover; no live database supplied |
| G05 | Exact AI Marketing Box and Tailor Law members, owner and designated reviewer; legal jurisdiction | Authorized onboarding, explicit brand grants, Tailor Law substantive-claim review. Do not create/invite guessed users | M1 onboarding/M2 legal editorial gates; pending |
| G06 | Provider accounts and approved processing/privacy terms | Candidate AI OpenAI, transcription Deepgram, avatar HeyGen, assembly Shotstack, storage R2/S3. Existing subscriptions may not include API entitlement | Relevant live gates; all unverified. Configure secrets through secure account tooling |
| G07 | Positive workspace/campaign/job production caps and bounded preproduction allowance | USD0 live spend until explicit owner budgets. Separate capped preproduction authorizations for drafting/transcription/sample generation; approved production plan for render/output jobs | First paid operation; BLOCKED, no amount invented |
| G08 | Exact social account IDs and intended LinkedIn type | Owner explicitly requires BOTH LinkedIn personal profiles and company pages; each needs separate OAuth capability and controlled-publication evidence. YouTube, professional Instagram, Facebook Page and TikTok remain required | Discovery now; M5 account gate. No silent account substitution |
| G09 | TikTok product eligibility and Direct Post audit | Describe actual intended self-service customer product honestly. Current guidelines prohibit utilities solely for accounts you/team manage; obtain eligibility confirmation/audit for public use | Early critical R1 risk; unresolved. No bypass, disguise or removal of fifth destination |
| G10 | Controlled live publications: exact account, material, timing, visibility, labels/consent and optional cleanup | Separate publication approval per pinned revision. Tests establish only approved visibility; private does not prove public eligibility. Deletion cleanup is separate authority | M5 real gate; no publications authorized |
| G11 | Avatar/voice IDs, rights and consent | Use explicitly approved stock/avatar/voice; record permitted uses, expiry and revocation | M4 real render; pending |
| G12 | At least ten permitted evaluation sources across both brands and rubric | Proposed 1–5 rubric: factual alignment, voice, format suitability, clip coherence, edit burden; mean >=4 each, no source <3, zero critical factual/rights failures | M2 sample/rubric approval and M6 UAT; pending, not a reason to block independent M1 work |
| G13 | Production retention and recovery policy | v6 planning: originals/approved until owner deletion, proxies30d, archives7d, audit/usage12mo, active purge<=7d, backups<=35d, RPO<=24h/RTO<=8h | Before production activation/purge and M6 restore; pending owner approval, no destructive purge |
| G14 | R2 subscription pricing, billing lifecycle and support policy | Keep pilot invitation-only/admin entitlements; no public signup or payment collection | M7 only; separate approved R2 specification |

## Immediate response requested

1. Approve the fresh npm network-access card: a retry after reported approval still returned a network-policy block.
2. Hosting/project was skipped and remains unknown. No existing identity service exists; a production identity recommendation still requires approval before provisioning. These do not prevent independent local backend work.
3. LinkedIn type is resolved: both personal and company. Actual account IDs, TikTok eligibility, consent/budgets and evaluation fixtures remain later gates.

Decision precedence: this owner-confirmed LinkedIn requirement supersedes optional/either-account wording in the earlier capability research and backlog. M5 acceptance must cover both account types; the five-platform scope is unchanged.

## Gate discipline

A missing credential/app review is BLOCKED, not passed. Continue independent local work without changing scope. Downloads do not satisfy direct publishing. Reviewable branch commits are authorized; merges, production deployment, spending, posts, invitations and destructive cutover are not authorized by plan approval. All AT scenarios remain unrun until the specified persisted-state evidence exists.

Official TikTok eligibility reference: https://developers.tiktok.com/doc/content-sharing-guidelines (researched 2026-09-11). Detailed official capability sources: PROVIDER_SOCIAL.md and PROVIDER_PRODUCTION.md.
