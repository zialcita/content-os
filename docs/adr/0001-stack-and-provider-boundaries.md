# ADR 0001 — Modular stack, explicit modes and provider boundaries

Date: 2026-09-11. Status: accepted engineering direction for M1 implementation; external/commercial choices remain conditional. Product authority: v6. No deployment or provider authorization is granted.

## Context

The baseline is a small FastAPI/SQLAlchemy and Next.js application with 14 tables, simulated adapters, synchronous pipelines and an in-process scheduler. Rewriting it into a new stack would discard useful domain/UI work without solving authorization, durability or immutable lineage. Baseline dependency manifests are not production lock policy. M0 measured existing tests and generated contracts; it did not implement the target runtime.

## Decisions

| Area | Resolved engineering default | Rationale / boundary |
|---|---|---|
| Application | Retain FastAPI, SQLAlchemy, Next.js/TypeScript; modular monolith with separately deployed API/web/worker processes | Reuse sound existing code; no per-provider microservices |
| Runtime | Python3.12 family, PostgreSQL16 family, Node24 LTS candidate; exact maintained patches validated/pinned per release | Baseline Python3.12.14 tested; frontend install remains blocked. Do not deploy old PG16.2 probe binary |
| API | Planned /api/v6 namespace alongside explicitly legacy /v1 during controlled migration | Avoid false compatibility; target OpenAPI stays separate from runtime /openapi.json until routes exist |
| Data | Additive cos_v6 schema; UUIDs, UTC timestamps, signed bigint micro-currency, composite tenant/brand FKs, sealed typed versions | ADR0002 defines normalized lineage, registry subtype integrity and migration. RLS defense in depth, never a substitute for role checks |
| Jobs | PostgreSQL row claims, lease heartbeat, fencing, durable steps, transaction outbox/dedup inbox | Queue authority survives Redis/API restart; Redis optional cache/rate limiting only |
| Sessions | FastAPI owns OIDC via maintained Authlib; opaque server-side PostgreSQL sessions; same-origin Next proxy | One identity authority, PKCE/state/nonce, issuer+subject binding, HttpOnly/Secure cookies, CSRF+Origin validation |
| Identity provider | Keycloak for isolated development integration; standards-based configurable issuer in production | No homemade passwords. Production provider/project must be approved; use an existing compliant issuer if supplied, no new hosting commitment by default |
| Storage | Private S3-compatible adapter; R2-compatible multipart, 16MiB parts, decimal 2GB cap, quarantine/scan/probe before use | Reuses boto3 boundary, avoids 2GB proxy requests. Production account/region/privacy approval is external |
| Structured AI | OpenAI structured-output adapter first candidate; server-owned schemas and pinned model/prompt/usage metadata | Compatible existing boundary; exact supported model selected through capability fixtures and approved account, never silently fallback to another paid provider |
| Transcription | Deepgram prerecorded candidate for diarized word timing; OpenAI whisper-1 alternative only via explicit configured choice | Timing/retention/callback semantics differ. Adapter interface selected, commercial/provider execution pending |
| Avatar | HeyGen first real adapter; capability-versioned API based on current official docs, not the legacy v2 TODO | Consent and pre-spend script approval required; uncertain submission enters RECONCILING |
| Assembly | Provider-neutral timeline compiler; Shotstack first cloud candidate, FFmpeg/ffprobe for local transformations and measured validation | Cloud capability/hosting/privacy proof remains pending, not accepted from documentation alone. No change of release scope |
| Social | Direct per-destination adapters; application owns approved intent and dispatch unless native scheduling explicitly proven | Five required destinations retained. Separate account identity, rendition/profile, remote state and intended-visibility verification |
| Modes | Production fails closed on absent/unimplemented provider; explicit test/development fixtures only | Simulation is never automatic failure recovery, provider spend or publication proof |
| Spending | Zero default live cap; atomic workspace/job/campaign applicable reservations before network writes | Distinguish preproduction capped work authorization from approved production plan. No pre-plan deadlock and no inferred allowance |
| Observability | Structured redacted logs, correlation IDs, audit, job/attempt dashboard, usage/connection/budget notifications | No fabricated percent progress; native metrics unavailable is null, not zero |

## Defaults carried forward, not owner-approved production policy

Private shared application with isolated workspaces; English first; v6 input/output sizing, role composition, 10 users/5 brands/100GB/2 paid jobs concurrency; 10-minute private signed URLs; 15-minute late-dispatch cutoff; retry at most three confirmed-safe submissions; 80% warning/100% block; -16 LUFS/-1dBTP export defaults measured before acceptance. Retention and recovery values are development planning assumptions until owner operational approval. No initial users, invites, reviewers or avatar identities are fabricated.

## Rejected approaches

Do not use workspace key as human identity, SQLite as concurrency evidence, JWT/localStorage role checks as sole authority, API process timers as scheduling, mutable 'latest' pointers during paid production, provider URLs as long-lived private storage, generic social aggregator as replacement for mandatory direct adapters, simulated success as live evidence, or auto-retry on ambiguous paid acceptance.

## Hosting recommendation and gate

Preserve the current container compatibility. Candidate topology: managed container web/API and separately scaled worker, managed PostgreSQL and private R2/S3. Render is an option because the repository already mentions it, NOT a selected/verified account or authorization to migrate. Prefer the owner's existing capable hosting project. Require account/project, region/data processing terms, cost cap, private networking, TLS callbacks, secrets and recovery owner before production provisioning. No production migration follows from M0 approval.

## Consequences and verification

Additional normalized tables and construction rules cost more than a JSON-only prototype but make exact approvals, cross-tenant checks and recovery testable. Full contract validation proves structure only. Before M1 acceptance run real PostgreSQL migration/isolation/reservation/worker-restart tests and OIDC lifecycle/CSRF tests. Before provider gates prove exact account permissions, media capability, callback verification, uncertain-outcome recovery and spend reconciliation. Research URLs and caveats: ../PROVIDER_PRODUCTION.md and ../PROVIDER_SOCIAL.md. Owner questions: ../DECISIONS_REQUIRED.md.

## 2026-09-11 implementation update
Registry access granted; Next15.5.25/React19.2.8 baseline build verified. Retain these versions and pin matching direct dependencies. The npm audit finding was confined to transitive PostCSS: use a targeted Next-to-PostCSS8.5.28 override rather than forced Next16 upgrade. Reinstalled, audited (zero reported findings) and rebuilt; no compatibility claim beyond measured checks. Alembic1.18.4 and dependencies are added to the backend tested lock. The cos_v6 foundation is a restricted LOCAL_SIMULATION subset, not a replacement production OIDC architecture or complete planned data catalog; see M1_FOUNDATION.md for the deliberate local principal bridge and remaining role/authority gates.
