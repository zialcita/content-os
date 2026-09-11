#!/usr/bin/env python3
"""Safe M0 baseline runner: no inherited application configuration or provider secrets.
Runs only against a fresh local temporary SQLite database. This is NOT PostgreSQL
migration/isolation/concurrency acceptance. Never accepts an external DATABASE_URL.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/m1/regression'


def clean_environment(temp):
    return {
        'PATH': os.defpath,
        'HOME': str(temp),
        'APP_ENV': 'test',
        'RUNTIME_MODE': 'simulation',
        'DATABASE_URL': 'sqlite:///' + str(temp / 'baseline.db'),
        'SPEND_LIMIT_USD': '25',  # simulated legacy test fixture, never live authorization
        'AI_API_KEY': '', 'HEYGEN_API_KEY': '', 'SHOTSTACK_API_KEY': '',
        'PEXELS_API_KEY': '', 'HIGGSFIELD_API_KEY': '',
        'GOOGLE_CLIENT_ID': '', 'GOOGLE_CLIENT_SECRET': '',
        'YOUTUBE_REFRESH_TOKEN': '', 'YOUTUBE_CHANNEL_ID': '',
        'AVATAR_ENGINE': 'simulated', 'BROLL_ENGINE': 'simulated',
        'ASSEMBLY_ENGINE': 'simulated', 'STORAGE_BACKEND': 'local',
        'LOCAL_STORAGE_DIR': str(temp / 'storage'),
        'REDIS_URL': 'redis://127.0.0.1:1/0',
        'PYTHONDONTWRITEBYTECODE': '1',
    }


def main():
    for candidate in (ROOT / '.env', ROOT / 'backend/.env', ROOT.parent / '.env'):
        if candidate.exists():
            raise SystemExit('Refusing baseline with an application .env present; use a clean checkout.')
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='contentos-m0-') as name:
        temp = Path(name)
        env = clean_environment(temp)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/m0_test_bootstrap.py'), str(ROOT / 'backend/tests'), '-q'],
                                cwd=temp, env=env, text=True, capture_output=True)
        (EVIDENCE / 'safe-baseline-pytest.log').write_text(result.stdout + result.stderr)
        info = {'python': sys.version, 'commit': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                'database': 'fresh temporary SQLite, deleted after run', 'providers': 'explicitly simulated with empty credentials',
                'test_exit_code': result.returncode, 'acceptance_class': 'legacy fixture regression only'}
        (EVIDENCE / 'safe-baseline-summary.json').write_text(json.dumps(info, indent=2) + '\n')
        print(result.stdout)
        if result.returncode: print(result.stderr, file=sys.stderr)
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
