import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from foundation.service import call

ROOT = Path(__file__).resolve().parents[2]


def migrate(connection, direction='upgrade'):
    config = Config(str(ROOT / 'backend/alembic.ini'))
    config.attributes['connection'] = connection
    getattr(command, direction)(config, 'head' if direction == 'upgrade' else 'base')


@pytest.fixture(scope='session')
def db():
    manifest = Path(os.environ['M1_DISPOSABLE_MANIFEST'])
    data = json.loads(manifest.read_text())
    temp_root = Path(data['root']).resolve()
    assert temp_root.name.startswith('contentos-m1-pg-')
    assert manifest.resolve().parent == temp_root
    url = make_url(data['dsn'])
    host = url.query.get('host', url.host)
    assert host and Path(host).resolve().is_relative_to(temp_root), 'Only disposable Unix socket PostgreSQL accepted'
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text('CREATE TABLE public.legacy_sentinel(id text PRIMARY KEY, payload text NOT NULL)'))
        c.execute(text("INSERT INTO public.legacy_sentinel VALUES ('legacy/string-id','preserve exactly')"))
        defaults_before = c.execute(text('SELECT oid,defaclrole,defaclnamespace,defaclobjtype,defaclacl::text FROM pg_default_acl ORDER BY oid')).all()
        migrate(c)
        assert c.execute(text('SELECT oid,defaclrole,defaclnamespace,defaclobjtype,defaclacl::text FROM pg_default_acl ORDER BY oid')).all() == defaults_before
    with engine.connect() as c:
        version = c.execute(text('SELECT version()')).scalar_one()
        assert 'PostgreSQL 16.2' in version
        evidence = {'server': version, 'schema_revision': '0001_m1_foundation', 'dsn_logged': False,
                    'environment': 'new pgserver temp directory; no dotenv; environment whitelist',
                    'tables': list(c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='cos_v6' ORDER BY tablename")).scalars()),
                    'row_security': [dict(row) for row in c.execute(text("SELECT relname,relrowsecurity,relforcerowsecurity FROM pg_class JOIN pg_namespace n ON n.oid=relnamespace WHERE n.nspname='cos_v6' AND relkind='r' ORDER BY relname")).mappings()]}
        assert len(evidence['tables']) == 19
        (ROOT / 'docs/evidence/m1/foundation/environment.json').write_text(json.dumps(evidence, indent=2))
    yield SimpleNamespace(engine=engine, url=url)
    engine.dispose()


@pytest.fixture
def tenant(db):
    w, b, other_b = uuid4(), uuid4(), uuid4()
    members = {}
    engines = {}
    with db.engine.begin() as c:
        c.execute(text('INSERT INTO cos_v6.workspaces(id,name) VALUES (:w,\'fixture only\')'), {'w': w})
        for label, roles in [('owner', []), ('admin', ['admin']), ('editor', ['editor']), ('viewer', ['viewer'])]:
            user, membership = uuid4(), uuid4()
            role = 'fixture_' + uuid4().hex
            c.execute(text('INSERT INTO cos_v6.users(id,display_name,status,verified_at) VALUES (:u,:n,\'ACTIVE\',clock_timestamp())'), {'u': user, 'n': label})
            c.execute(text('INSERT INTO cos_v6.user_identities(user_id,issuer,subject,authenticated_at) VALUES (:u,\'https://fixture.invalid\',:s,clock_timestamp())'), {'u': user, 's': str(user)})
            c.execute(text('INSERT INTO cos_v6.workspace_memberships(id,workspace_id,user_id,roles,state,verified_at) VALUES (:m,:w,:u,:r,\'ACTIVE\',clock_timestamp())'), {'m': membership, 'w': w, 'u': user, 'r': roles})
            # Generated role identifier only; trusted local cluster uses Unix socket trust auth.
            c.exec_driver_sql(f'CREATE ROLE {role} LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS')
            c.exec_driver_sql(f'GRANT cos_foundation_runtime TO {role}')
            c.execute(text('INSERT INTO cos_v6.database_principals VALUES (:r,:u)'), {'r': role, 'u': user})
            members[label] = membership
            engines[label] = create_engine(db.url.set(username=role), pool_size=2)
        c.execute(text("UPDATE cos_v6.workspaces SET state='ACTIVE',owner_membership_id=:m WHERE id=:w"), {'m': members['owner'], 'w': w})
        for brand in (b, other_b):
            c.execute(text('INSERT INTO cos_v6.brands(id,workspace_id,name) VALUES (:b,:w,\'fixture brand\')'), {'b': brand, 'w': w})
    for label in ('editor', 'viewer'):
        with engines['owner'].begin() as c:
            call(c, 'set_brand_grant', w, b, members[label], True, False, 'test fixture')
    result = SimpleNamespace(w=w, b=b, other_b=other_b, members=members, engines=engines, db=db)
    yield result
    for engine in engines.values():
        engine.dispose()


def invoke(t, routine, *args, actor='owner'):
    with t.engines[actor].begin() as c:
        return call(c, routine, *args).mappings().all()


def job(t, amount=100, actor='owner', cap=100):
    j = next(iter(invoke(t, 'enqueue', t.w, t.b, uuid4(), b'x' * 32, actor=actor)[0].values()))
    invoke(t, 'set_budget', t.w, None, 'USD', cap, 'fixture workspace cap')
    invoke(t, 'set_budget', t.w, j, 'USD', amount, 'fixture job cap')
    return j


def claim(t, actor='owner', seconds=30):
    return invoke(t, 'claim', t.w, t.b, uuid4(), seconds, actor=actor)[0]


def args(t, s):
    return (t.w, s['id'], s['lease_owner'], s['fencing_token'])
