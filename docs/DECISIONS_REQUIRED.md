# Decisions and external gates

Date: 2026-09-11. Routine implementation decisions are resolved in ADR0001/0002. This register asks only for facts/authority engineering cannot manufacture. No secret should be pasted into a chat or committed. Existing Hyperagent connections do not establish OAuth authority for the application being built.

| ID | Decision/input | Recommendation or safe default | Needed by / current status |
|---|---|---|---|
| G01 | Allow registry.npmjs.org dependency downloads | Approve the network-access request already surfaced; use existing lock, no alternate registry | M0 frontend install/build; BLOCKED E403 |
| G02 | Production OIDC issuer/provider and owner-controlled account/project | Authlib with Keycloak in isolated development; reuse your maintained production OIDC service if one exists | M1 real identity integration; owner selection/account access pending |
| G03 | Hosting project, region and operating cost ceiling | Retain container deployment; separate API/web/worker, managed PostgreSQL, private storage. Existing Render-compatible Dockerfile is not evidence of a deployment | Before provisioning or production deployment; pending. Local backend tests do not wait for this |
| G04 | Legacy data exists? Owner/brand mapping and historical timestamp provenance | Do not connect to a live database yet. Obtain an authorized sanitized inventory/backup; never infer owners by email or keys | M1 actual migration rehearsal/cutover; no live database supplied |
| G05 | Exact AI Marketing Box and Tailor Law members, owner and designated reviewer; legal jurisdiction | Authorized onboarding, explicit brand grants, Tailor Law substantive-claim review. Do not create/invite guessed users | M1 onboarding/M2 legal editorial gates; pending |
| G06 | Provider accounts and approved processing/privacy terms | Candidate AI OpenAI, transcription Deepgram, avatar HeyGen, assembly Shotstack, storage R2/S3. Existing subscriptions may not include API entitlement | Relevant live gates; all unverified. Configure secrets through secure account tooling |
| G07 | Positive workspace/campaign/job production caps and bounded preproduction allowance | USD0 live spend until explicit owner budgets. Separate capped preproduction authorizations for drafting/transcription/sample generation; approved production plan for render/output jobs | First paid operation; BLOCKED, no amount invented |
| G08 | Exact social account IDs and intended LinkedIn type | YouTube channel, LinkedIn personal OR organization as selected, professional Instagram, Facebook Page and TikTok creator. Both LinkedIn capabilities researched, not both required by assumption | Discovery now; M5 account gate. No silent account substitution |
| G09 | TikTok product eligibility and Direct Post audit | Describe actual intended self-service customer product honestly. Current guidelines prohibit utilities solely for accounts you/team manage; obtain eligibility confirmation/audit for public use | Early critical R1 risk; unresolved. No bypass, disguise or removal of fifth destination |
| G10 | Controlled live publications: exact account, material, timing, visibility, labels/consent and optional cleanup | Separate publication approval per pinned revision. Tests establish only approved visibility; private does not prove public eligibility. Deletion cleanup is separate authority | M5 real gate; no publications authorized |
| G11 | Avatar/voice IDs, rights and consent | Use explicitly approved stock/avatar/voice; record permitted uses, expiry and revocation | M4 real render; pending |
| G12 | At least ten permitted evaluation sources across both brands and rubric | Proposed 1–5 rubric: factual alignment, voice, format suitability, clip coherence, edit burden; mean >=4 each, no source <3, zero critical factual/rights failures | M2 sample/rubric approval and M6 UAT; pending, not a reason to block independent M1 work |
| G13 | Production retention and recovery policy | v6 planning: originals/approved until owner deletion, proxies30d, archives7d, audit/usage12mo, active purge<=7d, backups<=35d, RPO<=24h/RTO<=8h | Before production activation/purge and M6 restore; pending owner approval, no destructive purge |
| G14 | R2 subscription pricing, billing lifecycle and support policy | Keep pilot invitation-only/admin entitlements; no public signup or payment collection | M7 only; separate approved R2 specification |

## Immediate response requested

1. Approve npm registry access so the existing frontend baseline can be tested.
2. Confirm whether you already have an OIDC service and hosting project to reuse, or want a concrete costed recommendation before any provisioning.
3. Confirm the desired LinkedIn destination type and TikTok customer-use case. Account IDs, consent/budgets and evaluation fixtures can follow when their dependent gate is reached.

## Gate discipline

A missing credential/app review is BLOCKED, not passed. Continue independent local work without changing scope. Downloads do not satisfy direct publishing. Reviewable branch commits are authorized; merges, production deployment, spending, posts, invitations and destructive cutover are not authorized by plan approval. All AT scenarios remain unrun until the specified persisted-state evidence exists.

Official TikTok eligibility reference: https://developers.tiktok.com/doc/content-sharing-guidelines (researched 2026-09-11). Detailed official capability sources: PROVIDER_SOCIAL.md and PROVIDER_PRODUCTION.md.
