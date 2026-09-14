#!/usr/bin/env python3
"""Run foundation acceptance on a fresh local pgserver, never an inherited DSN.
Usage: python3.9 scripts/test_foundation_postgres.py .venv/bin/python3.12
No dotenv/application imports, provider credentials, remote DB or paid calls.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
from pgserver import get_server

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/m1/foundation'


def main():
    python = str(Path(sys.argv[1]).absolute())
    with tempfile.TemporaryDirectory(prefix='contentos-m1-pg-') as tmp:
        # Also scrub the environment inherited by pgserver's local server processes.
        os.environ.clear()
        os.environ.update({'PATH': os.defpath, 'HOME': tmp, 'PYTHON_DOTENV_DISABLED': '1'})
        server = get_server(Path(tmp) / 'pgdata', cleanup_mode='stop')
        try:
            uri = server.get_uri().replace('postgresql://', 'postgresql+psycopg://', 1)
            manifest = Path(tmp) / 'disposable.json'
            manifest.write_text(json.dumps({'dsn': uri, 'root': tmp}))
            env = {'PATH': os.defpath, 'HOME': tmp, 'PYTHONPATH': str(ROOT / 'backend'),
                   'M1_DISPOSABLE_MANIFEST': str(manifest), 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
                   'PYTHONDONTWRITEBYTECODE': '1', 'PYTHON_DOTENV_DISABLED': '1'}
            EVIDENCE.mkdir(parents=True, exist_ok=True)
            result = subprocess.run([python, '-m', 'pytest', '-c', '/dev/null',
                str(ROOT / 'backend/tests_foundation'), '--rootdir=' + str(ROOT), '-p', 'no:cacheprovider', '-v', '-ra', '--tb=short',
                '--junitxml=' + str(EVIDENCE / 'pytest.xml')],
                cwd=tmp, env=env, capture_output=True, text=True)
            (EVIDENCE / 'postgres-tests.log').write_text(result.stdout + result.stderr)
            print(result.stdout)
            print(result.stderr)
            print('Disposable foundation PostgreSQL tests exit:', result.returncode)
            return result.returncode
        finally:
            server._cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
