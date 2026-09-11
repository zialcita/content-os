# M0 reproducible local setup

Status: backend and contract baseline verified; frontend installation/build blocked by npm registry HTTP403 in the current environment. Do not call this a working v6 application. These commands are for an isolated development checkout, never a production database.

## Python baseline

Use Python3.12 (tested 3.12.14) and a fresh virtual environment:

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
.venv/bin/python scripts/verify_m0.py
.venv/bin/python scripts/snapshot_m0.py
```

requirements.lock is the exact M0 resolver result, including test dependencies, with version pins but no artifact hashes. requirements.txt remains the historical lower-bound input. Production dependency security review/hash lock and container pinning are M1 tasks. A TestClient deprecation warning is recorded, not hidden.

verify_m0.py sanitizes the child environment, uses a new local SQLite database, disables dotenv before imports, blanks provider credentials, and deliberately uses simulated engines. It never accepts an inherited or user-supplied DSN. Its fixture USD25 exists solely to run the historical simulation; it grants no live budget. The original tests use drop_all and must not be executed directly in a configured production environment.

## Real disposable PostgreSQL baseline

Install the exact pgserver version in docs/evidence/m0/probe-tools.txt into an isolated tooling environment; this packages a real PostgreSQL16.2 binary with vector, not an emulation. It is only a local baseline tool, not a production recommendation. Then:

```sh
python scripts/probe_m0_postgres.py "$PWD/.venv/bin/python"
```

The outer Python must have pgserver. The runner creates a fresh temporary PostgreSQL data directory/socket, obtains its generated DSN, explicitly passes that to the application/test subprocess, disables dotenv, runs init_db and the three original tests, records evidence, stops the owned local server and removes only its temporary data. No external DB connection is accepted. The source tests' setdefault cannot replace this DSN. PostgreSQL baseline passing does not demonstrate Alembic migrations, RLS, fencing, concurrency or v6 acceptance.

## Contract validation

Install docs/evidence/m0/m0-tools.lock into a separate Python3.12 venv or the baseline venv (it includes installed schema validators). Then:

```sh
.venv/bin/python docs/contracts/build_contracts.py --check
.venv/bin/python -m unittest discover -s docs/contracts -p 'test_*.py' -v
```

Current suite: 42 offline tests, no skips with the pinned validators installed. Generated OpenAPI is planned target only; do not serve it as implemented runtime documentation. Regenerate using build_contracts.py after changing the generator.

## Frontend baseline — pending network approval

```sh
npm ci --prefix frontend --ignore-scripts
NEXT_TELEMETRY_DISABLED=1 npm run build --prefix frontend
```

Preserve package-lock.json. The recorded environment is Node24.14.1/npm11.11.0. npm ci failed with HTTP403 at registry.npmjs.org/undici-types/-/undici-types-6.21.0.tgz; network access was requested. The attempted build then failed because next was unavailable. Do not regenerate the lock or change registries to conceal an access failure. After authorized access, retry install/build and record actual compiler/lint/type results; fix genuine code defects in reviewable changes.

## Evidence provenance

CURRENT_STATE.md names the inspected source commit. docs/evidence/m0 contains logs, runtime manifests, schema/OpenAPI snapshots and tool versions; scripts identify exactly how the artifacts were produced. Logs have no production credentials, signed URLs or operational database data. The legacy runtime is unchanged by M0; v6 runtime, CI, migrations and production fail-closed controls are later work.
