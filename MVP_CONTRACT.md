# Historical MVP contract — superseded by v6

This file is retained for historical context only. The binding product target is [CONTENT_OS_ASTRA_BUILD_SPEC_v6.md](docs/spec/CONTENT_OS_ASTRA_BUILD_SPEC_v6.md). The YouTube-only scope and simulated-fallback rules below do not govern v6 implementation. Original bytes are preserved at [docs/history/MVP_CONTRACT.pre-v6.md](docs/history/MVP_CONTRACT.pre-v6.md).

## Original contract (historical)

This repo implements **only** the v1 YouTube pillar pipeline. Do not expand scope.

## In v1

Vertical pipeline:

`script → HeyGen A-roll → B-roll (library → Pexels → Higgsfield) → Shotstack assembly → clips → YouTube`

Human checkpoints:

1. **Script approve** (`script_ready` → `script_approved`)
2. **Final-cut approve** (`in_review` → `approved`)

Video status machine:

`scripting → script_ready → script_approved → rendering_avatar → avatar_ready → resolving_broll → assembling → assembly_ready → in_review → approved → publishing → published` plus `failed`.

## Out of v1

- Multi-platform social
- Learning engine
- Client portal
- MCP
- Escalation
- Calendar scheduling

## Auth

- `POST /v1/workspaces` creates a workspace and returns a one-time API key.
- Authenticated routes use `X-API-Key`.

## Providers

Every paid/external system is an adapter with `is_configured()` and a **simulated fallback**. The app must run with zero provider keys.

Hard spend gate: `SPEND_LIMIT_USD` (copied onto the workspace) is checked before ledgered calls.

## Tables

workspaces, users, brands, personas, research_sources, evidence_items, avatar_profiles, video_projects, video_scenes, render_jobs, media_assets, clips, audit_logs, plus `cost_ledger` for the spend gate.
