#!/usr/bin/env python3
"""Snapshot source metadata/OpenAPI without starting app lifespan or provider calls."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/m0'
for p in (ROOT / '.env', ROOT / 'backend/.env', ROOT.parent / '.env'):
    if p.exists(): raise SystemExit('Use a clean checkout without application .env files')
os.environ.clear()
os.environ.update({'DATABASE_URL':'sqlite:///:memory:', 'APP_ENV':'test'})
sys.path.insert(0, str(ROOT / 'backend'))
from config import Settings, get_settings
Settings.model_config['env_file'] = None
get_settings.cache_clear()
from main import app
from database import Base
from models import entities
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
EVIDENCE.mkdir(parents=True, exist_ok=True)
(EVIDENCE / 'legacy.openapi.json').write_text(json.dumps(app.openapi(), indent=2) + '\n')
schema = []
for table in Base.metadata.sorted_tables:
    schema.append({'name':table.name, 'columns':[{'name':c.name,'type':str(c.type),'nullable':c.nullable,'primary_key':c.primary_key,'foreign_keys':sorted(f.target_fullname for f in c.foreign_keys)} for c in table.columns]})
(EVIDENCE / 'legacy.schema.json').write_text(json.dumps(schema, indent=2) + '\n')
(EVIDENCE / 'legacy.schema.sql').write_text('-- SQLAlchemy source-compiled PostgreSQL DDL; not an applied migration.\n' + '\n'.join(str(CreateTable(t).compile(dialect=postgresql.dialect()))+';' for t in Base.metadata.sorted_tables))
print(f'Snapshotted {len(schema)} legacy tables and {len(app.openapi()["paths"])} runtime-declared paths (lifespan NOT started)')
