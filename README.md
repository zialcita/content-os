# Content OS — v6 engineering build

**Master contract:** [CONTENT_OS_ASTRA_BUILD_SPEC_v6.md](docs/spec/CONTENT_OS_ASTRA_BUILD_SPEC_v6.md). The scope now includes isolated client workspaces, text and both video routes, review, downloads, calendar and five direct publishing destinations. The earlier YouTube-only exclusions below are historical, not current scope.

**Status: M0 local inventory/contracts/baseline gate passed. M1 foundation, legacy safety and a reviewed development identity API are implemented and locally tested; full M1 remains open. This application is not production-ready.** Provider account-level proofs remain external gates. See [M1 progress and evidence](docs/M1_PROGRESS.md).

## Engineering entry points

- [Current state and measured baseline](CURRENT_STATE.md)
- [Reviewed identity API checkpoint](docs/IDENTITY_REVIEW.md) and [identity setup/interfaces](docs/M1_IDENTITY_API.md)
- [Database design](docs/DATABASE_DESIGN.md) and [preservation-first migration plan](docs/MIGRATION_PLAN.md)
- [API/event contracts](docs/API_CONTRACTS.md): target schemas are design-only; runtime OpenAPI stays separate
- [Architecture/defaults](docs/adr/0001-stack-and-provider-boundaries.md) and [data/workers ADR](docs/adr/0002-data-and-workers.md)
- [Owner decisions and external gates](docs/DECISIONS_REQUIRED.md)
- [Milestone backlog](docs/MILESTONE_BACKLOG.md) and [acceptance matrix](docs/ACCEPTANCE_MATRIX.md)
- [Provider discovery: production](docs/PROVIDER_PRODUCTION.md) and [social](docs/PROVIDER_SOCIAL.md)
- [Safe local setup](docs/LOCAL_SETUP.md), [deployment readiness](DEPLOYMENT.md), [build log](BUILD_LOG.md)

Original documents are preserved verbatim in [docs/history](docs/history). Do not run the legacy tests against a configured application database: their fixture calls drop_all. Use the isolated runners in LOCAL_SETUP.md. Production startup is now deliberately refused. Development/test requires explicit simulation with empty provider credentials; the frontend labels fixture states and usage. Neither fixture budgets nor historical defaults authorize live spending.

---

## Historical README — describes the pre-v6 simulation only

The following quickstart and deployment claims are historical. They are not v6 operating instructions or deployment evidence.

YouTube-first content operating system. MVP is a **simulated** pillar pipeline:

**script → HeyGen A-roll → B-roll (library → Pexels → Higgsfield) → Shotstack → clips → YouTube**

Human gates: approve script, approve final cut.  
Out of v1: multi-platform social, learning engine, client portal, MCP, escalation, calendar. See [MVP_CONTRACT.md](MVP_CONTRACT.md).

The API runs with **zero provider keys**. Real HeyGen / Pexels / Higgsfield / Shotstack / R2 / YouTube calls are adapter stubs; simulated engines complete the path locally.

## Stack

- FastAPI + SQLAlchemy + PostgreSQL (pgvector image) + Redis
- Next.js App Router admin (Videos, Personas, Sources, Review)
- Cloudflare R2 via boto3, or local `./data`
- OpenAI-compatible LLM settings (`AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`)

## Quickstart

```bash
cp .env.example .env
docker compose up -d   # Postgres + Redis
```

### API

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Without Docker, skip compose and use SQLite:

```bash
export DATABASE_URL=sqlite:///./data/contentos.db
uvicorn main:app --reload --port 8000
```

Health check:

```bash
curl -s http://localhost:8000/health
```

Create a workspace (returns the API key once):

```bash
curl -s -X POST http://localhost:8000/v1/workspaces \
  -H 'content-type: application/json' \
  -d '{"name":"Demo Studio"}'
```

### Simulated pipeline

```bash
export KEY=cos_...   # from the create-workspace response

curl -s -X POST http://localhost:8000/v1/videos \
  -H "X-API-Key: $KEY" -H 'content-type: application/json' \
  -d '{"title":"Ship the cut","topic":"content systems"}'

# then, with VIDEO_ID from the response:
curl -s -X POST http://localhost:8000/v1/videos/$VIDEO_ID/approve-script -H "X-API-Key: $KEY"
curl -s -X POST http://localhost:8000/v1/videos/$VIDEO_ID/resolve-broll -H "X-API-Key: $KEY"
curl -s -X POST http://localhost:8000/v1/videos/$VIDEO_ID/assemble -H "X-API-Key: $KEY"
curl -s -X POST http://localhost:8000/v1/videos/$VIDEO_ID/approve -H "X-API-Key: $KEY"
curl -s -X POST http://localhost:8000/v1/videos/$VIDEO_ID/publish -H "X-API-Key: $KEY"
curl -s http://localhost:8000/v1/videos/$VIDEO_ID/clips -H "X-API-Key: $KEY"
```

Create → `script_ready`. Approve script → simulated A-roll → `avatar_ready`. Resolve B-roll / assemble → `in_review`. Approve cut → publish → `published` + clips.

A ~60s asyncio scheduler ticks leftover queued render jobs (Redis lock if Redis is up).

### Admin UI

```bash
cd frontend
npm install
echo 'NEXT_PUBLIC_API_URL=http://localhost:8000' > .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The first screen creates a workspace and stores the key in `localStorage`.

### Tests

```bash
cd backend && pytest -q
```

## Render

`backend/Dockerfile` is Render-ready. Set `DATABASE_URL`, `REDIS_URL`, and `SPEND_LIMIT_USD`. Provider keys are optional.

## Environment

See `.env.example` for `HEYGEN_*`, `HIGGSFIELD_*`, `PEXELS_*`, `SHOTSTACK_*`, `S3_*` / R2, `AI_*`, `GOOGLE_*` / `YOUTUBE_*`, `DATABASE_URL`, `REDIS_URL`, `SPEND_LIMIT_USD`.
