# M1 legacy runtime safety slice

## Status and scope

**Implemented local safety boundary, not completed M1 or production readiness.** Read against the complete `docs/spec/CONTENT_OS_ASTRA_BUILD_SPEC_v6.md`, especially §§3–4, 7, 13–16, 19, 21–22 (AT-01, AT-27, AT-29).

Starting commit inspected: `0534244dc751c2b802f516875519aa7ed2d0f505`, branch `engineering/v6-m0-foundation`. This evidence describes the working-tree safety changes, not an assertion that they are committed or deployed. Existing M0 evidence is preserved by the parent orchestrator.

This slice changes only legacy configuration, API startup, legacy accounting, health/tick routes and tests. The separate `backend/foundation`, Alembic, fixed-precision reservations, durable workers and foundation tests are owned by the other implementation slice and were not edited here. No dependency, frontend, deployment, GitHub, provider, publication or spending action was performed.

## Fail-closed contract

| Configuration/action | Result |
|---|---|
| No environment configuration | Defaults to `APP_ENV=production`, `RUNTIME_MODE=blocked`, `SPEND_LIMIT_USD=0`; import refuses |
| `APP_ENV=production`, any runtime mode | Typed `LEGACY_PRODUCTION_DISABLED`, HTTP-equivalent 503; no override |
| Any environment other than exact `production`, `development`, `test` | Typed `UNSUPPORTED_ENVIRONMENT`; typos/case/whitespace cannot bypass |
| `development` / `test` without exact `RUNTIME_MODE=simulation` | Typed `SIMULATION_OPT_IN_REQUIRED` |
| Explicit simulation with real engine selection, nonlocal storage, or provider/account credentials | Typed `LIVE_CONFIGURATION_FORBIDDEN`; values are not echoed |
| Explicit development/test simulation, simulated engines, local storage, no provider credentials | Legacy fixture API may initialize its isolated database and serve requests |
| `POST /v1/jobs/tick`, any key or no key | Always disabled; `GLOBAL_TICK_DISABLED` 503 in runnable modes; production middleware/startup refuses first |

`main.py` evaluates policy **before importing database, routers or scheduler**, so production cannot construct the legacy engine, run `create_all`, register simulated routes or start background work. Lifespan checks again before initialization; request middleware checks again before route dependencies, including clients that skip ASGI lifespan. Error details contain `code`, `message`, `field_errors`, `retryable=false`, and a generated `correlation_id`.

There is intentionally **no `V6_READY` / migrations-ready / OIDC-ready / worker-ready environment bypass**. Genuine integration and reviewed code changes are required. Creating foundation modules alone must not unlock the legacy entry point.

The in-process scheduler is no longer started **in any legacy API mode**. The unsafe tick endpoint has no auth/database dependency and does not import or call the scheduler. Queued work is not automatically advanced by this API. Existing synchronous fixture pipeline behavior remains; durable operational execution must arrive through the separate authorized worker integration, not a workspace API key.

## Explicit simulation and honest labels

A fixture runtime requires all of:

```text
APP_ENV=test                 # or development, never production
RUNTIME_MODE=simulation
AVATAR_ENGINE=simulated
BROLL_ENGINE=simulated
ASSEMBLY_ENGINE=simulated
STORAGE_BACKEND=local
SPEND_LIMIT_USD=25            # optional fixture allowance; default is zero
```

Use a disposable database/storage directory, clear inherited configuration and disable dotenv loading in tests. No live credentials may be supplied. Engine defaults alone do not authorize simulation; the explicit runtime mode is mandatory. Configured-but-unimplemented adapters are rejected instead of silently falling back.

Visibility:

- OpenAPI title/description explicitly identify legacy simulation.
- `/health` and `/v1/health` include `runtime_mode=simulation`, `production_ready=false`, `usage_kind=simulation_not_provider_spend`, `publication_kind=simulation_not_live`, and `global_tick_enabled=false`.
- API responses expose `X-ContentOS-Mode: simulation` and `X-ContentOS-Usage: simulation-not-provider-spend`, including CORS exposure for clients.
- Newly recorded legacy fixture ledger entries have `provider=simulated` and an operation prefixed `simulation.`. Real-provider labels cannot settle through this ledger; zero-cost local library reuse is recorded as fixture usage.
- Legacy `spend_usd`, positive fixture amounts, `published` statuses and simulated YouTube-shaped URLs remain for compatibility. **They are not provider charges, playable/rendered-media evidence, or live publication evidence.** No existing records are relabeled/destructively rewritten by this slice. Migration/reconciliation of historical records remains required.

The three baseline test assertions are unchanged; only their startup environment was changed to explicit, disposable simulation. Their USD25 allowance is test-fixture accounting, not owner approval for paid work.

## Budget behavior and limits

`Settings.spend_limit_usd` now defaults to zero and rejects negative/nonfinite configured values. The API-created workspace receives that configured value. A workspace limit of zero never falls back to another positive limit; only an absent (`None`) workspace value may inherit configuration. A zero-cost fixture operation may proceed at zero, while any positive fixture amount is blocked. Invalid negative/nonfinite usage/cap values refuse with `INVALID_BUDGET`.

Budget refusal preserves legacy HTTP 402 / `error=spend_limit_exceeded` behavior and adds canonical `code=BUDGET_EXCEEDED` with structured error fields and simulation classification. Zero-budget API tests verify failed work leaves no video, job or ledger entries.

**The legacy ledger still uses binary floats and a non-atomic read/update sequence. It is not production-safe, does not reserve funds before dispatch, and is not a v6 provider-cost ledger.** The legacy ORM model's historical USD25 default also remains outside this slice; the API creation path overrides it with configured zero. These are additional reasons production is blocked, not evidence of financial correctness. The other slice owns fixed-precision, atomic reserve/settle/release and database concurrency proof. Do not import positive legacy fixture counters as real spend.

## Test isolation and reproducible evidence

Run from any working directory using the repository virtual environment:

```sh
/agent/workspace/content-os/.venv/bin/python \
  /agent/workspace/content-os/docs/evidence/m1/runtime-safety/run_safe_tests.py
```

The bootstrap clears all inherited environment settings, selects a temporary SQLite database/storage directory, disables pytest third-party plugin autoload, sets `Settings.model_config['env_file'] = None` and clears the settings cache **before application imports**, and forbids outbound socket connection calls. It executes only the two owned legacy test files. The baseline test module independently uses a temporary directory, synthetic environment and disabled dotenv before importing `database` or `main`, so `drop_all` never targets inherited settings. Application integration regressions each use a clean subprocess with their own synthetic environment/disposable SQLite database and blocked network. A hostile synthetic parent environment plus `.env` test proves those sources are not used.

Evidence under `docs/evidence/m1/runtime-safety/`:

- `run_safe_tests.py` — reproducible safe bootstrap.
- `pytest.log` — full named test results.
- `pytest.xml` — machine-readable JUnit results.
- `evidence.json` — run result and SHA-256 hashes of this slice's source files.

**Result: 59 passed, 0 failed, 0 skipped** (3 existing pipeline cases + 56 runtime-safety parameterized cases). One upstream Starlette/httpx deprecation warning remains; dependencies were not changed. The evidence log has the exact duration/interpreter/pytest versions.

Tests cover production/default refusal; unsupported environments; explicit development/test opt-in; rejection of configured stubs/credential-selected fallbacks without secret echo; refusal before DB/router/scheduler import even with fake readiness flags; lifespan and request rechecks; visible fixture labels/no scheduler; two workspaces with queued jobs whose video/job/ledger/counter state stays unchanged after both keys, invalid key and anonymous tick attempts; hard-zero cap and transaction rollback; fixture-ledger labeling; invalid budget numbers; forbidden real-provider settlement; and inherited-env/dotenv isolation. All data and credentials are synthetic. No paid call or external publication occurred.

## Remaining release/integration gates

1. Wire the real v6 migration chain and validated PostgreSQL schema into a non-legacy application entry point; no startup `create_all` in production. Prove tenant constraints and upgrade/rollback preservation.
2. Integrate actual OIDC/session verification, memberships/brand grants, CSRF, revocation and restricted credential authorization before exposing application mutations.
3. Integrate dedicated durable workers/outbox, lease/fencing/restart/reconciliation behavior and authorized operations. Do not re-enable a global HTTP tick for workspace keys.
4. Integrate the fixed-precision atomic budget ledger before any provider dispatch; validate concurrent PostgreSQL reservations/settlements, explicit currency and simulation separation. These tests do not substitute for AT-05 or a financial gate.
5. Implement/configure real providers without fallback, owner-entered live budget, and versioned approvals/consent. Real provider outcomes and controlled publications require separate explicit authorization and evidence.
6. Foundation PostgreSQL tests, migrations, OIDC account provisioning, real provider/media/publishing acceptance, restore/deployment and complete R1 acceptance are **not proven by this slice**.

Integration caution: `main` import now deliberately fails with default settings. Any contract-generation script, developer launcher or test importing it must explicitly opt into isolated simulation or target the future secure entry point. The old README/env-example defaults were outside this slice and may need parent-owned follow-up. Keep legacy and foundation test suites isolated rather than allowing the legacy module's synthetic environment to overwrite a foundation suite's intended database configuration in a shared test process.
