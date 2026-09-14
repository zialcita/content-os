#!/usr/bin/env python3
"""Fresh local PostgreSQL identity acceptance. Outer Python 3.9 has pgserver.
Usage: python3.9 scripts/test_identity_postgres.py .venv/bin/python
Never inherits dotenv/DATABASE_URL or calls real providers.
"""
from pathlib import Path
import json
import hashlib
import os
import subprocess
import sys
import tempfile
from pgserver import get_server

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/m1/identity'


def main():
    python = str(Path(sys.argv[1]).absolute())
    with tempfile.TemporaryDirectory(prefix='contentos-identity-pg-') as tmp:
        os.environ.clear()
        os.environ.update({'PATH': os.defpath, 'HOME': tmp, 'PYTHON_DOTENV_DISABLED': '1'})
        server = get_server(Path(tmp) / 'pgdata', cleanup_mode='stop')
        try:
            uri = server.get_uri().replace('postgresql://', 'postgresql+psycopg://', 1)
            manifest = Path(tmp) / 'disposable.json'
            manifest.write_text(json.dumps({'dsn': uri, 'root': tmp}))
            env = {'PATH': os.defpath, 'HOME': tmp, 'PYTHONPATH': str(ROOT / 'backend'),
                   'IDENTITY_DISPOSABLE_MANIFEST': str(manifest), 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
                   'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1'}
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            sources = sorted(list((ROOT / 'backend/secure_api').glob('*.py')) +
                list((ROOT / 'backend/secure_api').glob('*.sql')) +
                list((ROOT / 'backend/tests_identity').glob('*.py')) +
                [ROOT / 'backend/alembic/versions/0002_sessions.py', Path(__file__).resolve(),
                 ROOT / 'docs/M1_IDENTITY_API.md', ROOT / 'docs/spec/CONTENT_OS_ASTRA_BUILD_SPEC_v6.md',
                 ROOT / 'docs/API_CONTRACTS.md', ROOT / 'docs/DATABASE_DESIGN.md',
                 ROOT / 'backend/foundation/schema.sql', ROOT / 'backend/foundation/privileges.py',
                 ROOT / 'backend/foundation/migration_audit.py', ROOT / 'backend/alembic/env.py',
                 ROOT / 'backend/requirements.lock'])
            hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
            (EVIDENCE / 'source-manifest.json').write_text(json.dumps({'baseline': 'e5bc4dde0aee434743704ccefb7f0c1fec5189ff',
                'command': 'python3 scripts/test_identity_postgres.py .venv/bin/python',
                'fixture_only': True, 'sha256': hashes}, indent=2))
            result = subprocess.run([python, '-m', 'pytest', '-c', '/dev/null',
                str(ROOT / 'backend/tests_identity'), '--rootdir=' + str(ROOT), '-p', 'no:cacheprovider', '-v', '-ra', '--tb=short',
                '--junitxml=' + str(EVIDENCE / 'pytest.xml')], cwd=tmp, env=env, capture_output=True, text=True)
            (EVIDENCE / 'postgres-tests.log').write_text(result.stdout + result.stderr)
            print(result.stdout)
            print(result.stderr)
            print('Disposable identity PostgreSQL tests exit:', result.returncode)
            return result.returncode
        finally:
            server._cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
