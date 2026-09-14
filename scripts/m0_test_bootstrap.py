#!/usr/bin/env python3
"""Test-only bootstrap. Disable dotenv before any Settings instance/app import.
Caller MUST provision a disposable database and sanitize process environment.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from config import Settings, get_settings
Settings.model_config['env_file'] = None
get_settings.cache_clear()

if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main(sys.argv[1:]))
