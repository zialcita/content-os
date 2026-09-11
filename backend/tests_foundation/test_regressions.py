"""Reviewer regressions exercised against the same disposable real PostgreSQL."""
import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from conftest import ROOT, args, claim, invoke, job, migrate
from foundation.privileges import RUNTIME_FUNCTIONS, audit_function_privileges
from foundation.service import call


@pytest.mark.parametrize('isolation', ['READ COMMITTED', 'REPEATABLE READ', 'SERIALIZABLE'])
def test_snapshot_before_committed_revoke_cannot_reserve(tenant, isolation):
    t = tenant
    job(t, actor='editor')
    s = claim(t, actor='editor')
    with t.engines['editor'].connect().execution_options(isolation_level=isolation) as user:
        # Establish a transaction snapshot without invoking the new actor guard.
        pid = user.execute(text('SELECT pg_backend_pid(), txid_current_snapshot()')).one()[0]
        assert user.execute(text('SHOW transaction_isolation')).scalar_one() == isolation.lower()
        with t.engines['owner'].begin() as owner:
            assert owner.execute(text('SELECT pg_backend_pid()')).scalar_one() != pid
            call(owner, 'set_brand_grant', t.w, t.b, t.members['editor'], False, False,
                 'committed revoke after worker snapshot').all()
        expected = 'forbidden' if isolation == 'READ COMMITTED' else 'requires READ COMMITTED'
        with pytest.raises(DBAPIError, match=expected):
            # Direct SQL deliberately bypasses the Python wrapper.
            user.execute(text('SELECT cos_v6.reserve(:w,:s,:worker,:token,\'USD\',1)'),
                         dict(w=t.w, s=s['id'], worker=s['lease_owner'], token=s['fencing_token']))
        user.rollback()
    with t.db.engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM cos_v6.budget_reservations WHERE workspace_id=:w'), {'w': t.w}).scalar_one() == 0
        assert c.execute(text('SELECT sum(reserved_micros) FROM cos_v6.budget_accounts WHERE workspace_id=:w'), {'w': t.w}).scalar_one() == 0


@pytest.mark.parametrize('isolation', ['REPEATABLE READ', 'SERIALIZABLE'])
def test_actor_and_rls_reject_unsupported_isolation(tenant, isolation):
    for sql in ('SELECT cos_v6.actor()', 'SELECT id FROM cos_v6.brands'):
        with tenant.engines['editor'].connect().execution_options(isolation_level=isolation) as c:
            with pytest.raises(DBAPIError, match='requires READ COMMITTED'):
                c.execute(text(sql)).all()
            c.rollback()


def snapshot(t, table):
    with t.db.engine.connect() as c:
        return c.execute(text(f'SELECT to_jsonb(x) FROM cos_v6.{table} x WHERE workspace_id=:w ORDER BY to_jsonb(x)::text'), {'w': t.w}).scalars().all()


@pytest.mark.parametrize('field', ['worker', 'seconds'])
def test_null_claim_rejected_without_mutation(tenant, field):
    t = tenant
    job(t)
    before = {table: snapshot(t, table) for table in ('job_steps', 'production_jobs', 'job_transitions')}
    with pytest.raises(DBAPIError, match='invalid lease'):
        invoke(t, 'claim', t.w, t.b, None if field == 'worker' else uuid4(),
               None if field == 'seconds' else 30)
    assert before == {table: snapshot(t, table) for table in before}
    assert claim(t)['status'] == 'RUNNING'


@pytest.mark.parametrize('field', ['worker', 'seconds', 'token'])
def test_null_heartbeat_rejected_without_mutation(tenant, field):
    t = tenant
    job(t)
    s = claim(t)
    before = snapshot(t, 'job_steps')
    with pytest.raises(DBAPIError, match='invalid lease|stale fence'):
        invoke(t, 'heartbeat', t.w, s['id'], None if field == 'worker' else s['lease_owner'],
               None if field == 'token' else s['fencing_token'], None if field == 'seconds' else 30)
    assert before == snapshot(t, 'job_steps')


@pytest.mark.parametrize('field', ['worker', 'seconds'])
def test_null_outbox_claim_rejected_without_mutation(tenant, field):
    t = tenant
    job(t)
    s = claim(t)
    invoke(t, 'reserve', *args(t, s), 'USD', 1)
    invoke(t, 'complete', *args(t, s), 1)
    before = snapshot(t, 'event_outbox')
    with pytest.raises(DBAPIError, match='invalid lease'):
        invoke(t, 'claim_event', t.w, None if field == 'worker' else uuid4(),
               None if field == 'seconds' else 30)
    assert before == snapshot(t, 'event_outbox')
    e = invoke(t, 'claim_event', t.w, uuid4(), 30)[0]
    delivering = snapshot(t, 'event_outbox')
    # Validation must also reject NULL on a DELIVERING event, even if none is eligible.
    with pytest.raises(DBAPIError, match='invalid lease'):
        invoke(t, 'claim_event', t.w, uuid4(), None)
    assert delivering == snapshot(t, 'event_outbox')
    for worker, token in ((None, e['fencing_token']), (e['lease_owner'], None)):
        with pytest.raises(DBAPIError, match='stale event fence'):
            invoke(t, 'ack_event', t.w, e['event_id'], worker, token)
        assert delivering == snapshot(t, 'event_outbox')
    invoke(t, 'ack_event', t.w, e['event_id'], e['lease_owner'], e['fencing_token'])


@pytest.mark.parametrize('table,state_column,active,inactive', [
    ('job_steps', 'status', 'RUNNING', 'QUEUED'),
    ('event_outbox', 'state', 'DELIVERING', 'PENDING'),
])
def test_lease_owner_expiry_state_constraints(tenant, table, state_column, active, inactive):
    t = tenant
    job(t)
    s = claim(t)
    if table == 'event_outbox':
        invoke(t, 'reserve', *args(t, s), 'USD', 1)
        invoke(t, 'complete', *args(t, s), 1)
    before = snapshot(t, table)
    for state, worker, expiry in ((active, None, None), (active, uuid4(), None),
                                  (active, None, 'clock_timestamp()'),
                                  (inactive, uuid4(), 'clock_timestamp()')):
        with pytest.raises(DBAPIError, match='check constraint'):
            with t.db.engine.begin() as c:
                c.execute(text(f'UPDATE cos_v6.{table} SET {state_column}=:state, lease_owner=:worker, '
                               f'lease_expires_at={expiry or "NULL"} WHERE workspace_id=:w'),
                          dict(state=state, worker=worker, w=t.w))
        assert before == snapshot(t, table)


def test_current_routines_have_exact_runtime_allowlist_and_no_public_execute(db):
    with db.engine.begin() as c:
        audit_function_privileges(c)
        actual = set(c.execute(text('''SELECT proname || '(' || replace(oidvectortypes(proargtypes), ', ', ',') || ')'
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
            WHERE n.nspname='cos_v6' AND has_function_privilege('cos_foundation_runtime',p.oid,'EXECUTE')''')).scalars())
        assert actual == RUNTIME_FUNCTIONS
        migrate(c)  # A clean head rerun is audited and succeeds.


def test_head_audit_detects_new_default_public_definer_and_runtime_grant(db):
    name = 'unsafe_' + uuid4().hex
    with db.engine.begin() as c:
        c.exec_driver_sql(f'CREATE FUNCTION cos_v6.{name}() RETURNS int LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$ SELECT 1 $$')
    try:
        with pytest.raises(RuntimeError, match='PUBLIC EXECUTE=.*' + name):
            with db.engine.begin() as c:
                # No manually added GRANT: the global default is the vulnerability.
                migrate(c)
        with db.engine.begin() as c:
            c.exec_driver_sql(f'REVOKE EXECUTE ON FUNCTION cos_v6.{name}() FROM PUBLIC')
            c.exec_driver_sql(f'GRANT EXECUTE ON FUNCTION cos_v6.{name}() TO cos_foundation_runtime')
        with pytest.raises(RuntimeError, match='unallowlisted runtime=.*' + name):
            with db.engine.begin() as c:
                migrate(c)
        with db.engine.begin() as c:
            c.exec_driver_sql(f'REVOKE EXECUTE ON FUNCTION cos_v6.{name}() FROM cos_foundation_runtime')
            migrate(c)
    finally:
        with db.engine.begin() as c:
            c.exec_driver_sql(f'DROP FUNCTION cos_v6.{name}()')


def test_future_revision_unsafe_definer_fails_before_migration_commit(db, tmp_path):
    revision = tmp_path / '0002_unsafe.py'
    revision.write_text('''from alembic import op
revision = '0002_unsafe'
down_revision = '0001_m1_foundation'
branch_labels = None
depends_on = None
def upgrade():
    op.execute("CREATE FUNCTION cos_v6.unsafe_future() RETURNS int LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$ SELECT 1 $$")
def downgrade():
    raise RuntimeError('not used')
''')
    config = Config(str(ROOT / 'backend/alembic.ini'))
    config.set_main_option('path_separator', 'os')
    config.set_main_option('version_locations', os.pathsep.join((str(ROOT / 'backend/alembic/versions'), str(tmp_path))))
    with pytest.raises(RuntimeError, match='PUBLIC EXECUTE=.*unsafe_future'):
        with db.engine.begin() as c:
            config.attributes['connection'] = c
            command.upgrade(config, 'head')
    with db.engine.begin() as c:
        assert c.execute(text("SELECT to_regprocedure('cos_v6.unsafe_future()')")).scalar_one() is None
        assert c.execute(text('SELECT version_num FROM public.cos_v6_alembic_version')).scalar_one() == '0001_m1_foundation'
        migrate(c)
