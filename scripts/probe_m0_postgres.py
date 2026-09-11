#!/usr/bin/env python3
"""Disposable PostgreSQL baseline probe; pgserver packages real local PostgreSQL.
Install pgserver in this interpreter, pass a Python with backend requirements.
No remote connection or application database is accepted. Does not bypass vector.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
from pgserver import get_server

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/m0'
python = sys.argv[1]
with tempfile.TemporaryDirectory(prefix='contentos-m0-pg-') as tmp:
    server = get_server(Path(tmp) / 'pgdata', cleanup_mode='stop')
    uri = server.get_uri().replace('postgresql://', 'postgresql+psycopg://', 1)
    env = {'PATH': os.defpath, 'HOME': tmp, 'DATABASE_URL': uri, 'APP_ENV': 'test',
           'PYTHONPATH': str(ROOT / 'backend'), 'SPEND_LIMIT_USD': '0'}
    code = '''import json
from sqlalchemy import text
from config import Settings, get_settings
Settings.model_config['env_file'] = None
get_settings.cache_clear()
from database import engine, init_db
with engine.connect() as conn:
 print(json.dumps({'server':conn.execute(text('select version()')).scalar(), 'extensions_available':list(conn.execute(text('select name from pg_available_extensions')).scalars())}))
try:
 init_db()
except Exception as e:
 print(type(e).__name__ + ': ' + str(e))
 raise SystemExit(1)
print('Legacy init_db succeeded on disposable PostgreSQL')
'''
    result = subprocess.run([python, '-c', code], cwd=tmp, env=env, capture_output=True, text=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / 'postgres-baseline.log').write_text(result.stdout + result.stderr)
    print(result.stdout)
    print('PostgreSQL legacy init exit:', result.returncode)
    if result.returncode == 0:
        env.update({'SPEND_LIMIT_USD': '25', 'AVATAR_ENGINE': 'simulated',
                    'BROLL_ENGINE': 'simulated', 'ASSEMBLY_ENGINE': 'simulated',
                    'AI_API_KEY': '', 'HEYGEN_API_KEY': '', 'SHOTSTACK_API_KEY': '',
                    'GOOGLE_CLIENT_ID': '', 'YOUTUBE_REFRESH_TOKEN': '',
                    'REDIS_URL': 'redis://127.0.0.1:1/0'})
        result = subprocess.run([python, str(ROOT / 'scripts/m0_test_bootstrap.py'), str(ROOT / 'backend/tests'), '-q'],
                                cwd=tmp, env=env, capture_output=True, text=True)
        (EVIDENCE / 'postgres-pytest.log').write_text(result.stdout + result.stderr)
        print(result.stdout)
        print('Disposable PostgreSQL legacy tests exit:', result.returncode)
    server._cleanup()
    # Probe reports failure honestly. It neither skips the extension nor alters legacy code.
    raise SystemExit(result.returncode)
