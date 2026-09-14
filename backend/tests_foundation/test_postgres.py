"""Real PostgreSQL acceptance; no SQLite/mocked engine/provider/network calls."""
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from foundation.service import call
from conftest import args, claim, invoke, job, migrate


def scalar(t, sql, params=None):
    with t.db.engine.connect() as c:
        return c.execute(text(sql), params or {'w': t.w}).scalar_one()


def test_additive_upgrade_twice_and_retention_safe_downgrade(db):
    with db.engine.begin() as c:
        migrate(c)
        assert c.execute(text('SELECT payload FROM public.legacy_sentinel')).scalar_one() == 'preserve exactly'
        assert c.execute(text('SELECT version_num FROM public.cos_v6_alembic_version')).scalar_one() == '0001_m1_foundation'
    with pytest.raises(RuntimeError, match='Retention-safe'):
        with db.engine.begin() as c:
            migrate(c, 'downgrade')
    with db.engine.connect() as c:
        assert c.execute(text('SELECT count(*) FROM public.legacy_sentinel')).scalar_one() == 1
        assert c.execute(text("SELECT to_regclass('cos_v6.usage_ledger')")).scalar_one()


def test_runtime_is_nonowner_nonbypass_and_no_direct_sensitive_dml(tenant):
    t = tenant
    with t.engines['owner'].connect() as c:
        assert c.execute(text('SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user')).scalar_one() is False
        assert c.execute(text("SELECT tableowner=current_user FROM pg_tables WHERE schemaname='cos_v6' AND tablename='brands'")).scalar_one() is False
        tables = c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='cos_v6'")).scalars().all()
        for table in tables:
            assert c.execute(text("SELECT has_table_privilege(current_user,:t,'INSERT,UPDATE,DELETE,TRUNCATE')"), {'t': 'cos_v6.' + table}).scalar_one() is False
    with pytest.raises(DBAPIError):
        with t.engines['owner'].begin() as c:
            c.execute(text('UPDATE cos_v6.workspaces SET owner_membership_id=:m WHERE id=:w'), {'m': t.members['admin'], 'w': t.w})
    with pytest.raises(DBAPIError):
        with t.engines['owner'].begin() as c:
            c.execute(text('SELECT cos_v6.settle_internal(:w,:s,1,false)'), {'w': t.w, 's': uuid4()})


def test_rls_missing_context_cross_tenant_and_guc_spoof(tenant):
    t = tenant
    with t.engines['editor'].begin() as c:
        c.execute(text("SELECT set_config('cos.actor_id',:u,true)"), {'u': str(t.members['owner'])})
        assert set(c.execute(text('SELECT id FROM cos_v6.brands')).scalars()) == {t.b}
    # Fresh pooled transaction retains no chosen user context; spoof never grants access.
    with t.engines['editor'].begin() as c:
        assert set(c.execute(text('SELECT id FROM cos_v6.brands')).scalars()) == {t.b}
    with t.engines['admin'].begin() as c:
        assert c.execute(text('SELECT count(*) FROM cos_v6.brands')).scalar_one() == 0
    role = 'unbound_' + uuid4().hex
    with t.db.engine.begin() as c:
        c.exec_driver_sql(f'CREATE ROLE {role} LOGIN INHERIT NOSUPERUSER NOBYPASSRLS')
        c.exec_driver_sql(f'GRANT cos_foundation_runtime TO {role}')
    unbound = create_engine(t.db.url.set(username=role))
    with unbound.begin() as c:
        c.execute(text("SELECT set_config('cos.actor_id',:u,true)"), {'u': str(t.members['owner'])})
        assert c.execute(text('SELECT count(*) FROM cos_v6.workspaces')).scalar_one() == 0
    unbound.dispose()


def test_pending_unclaimed_never_implicitly_active(tenant):
    for state in ('PENDING_ONBOARDING', 'LEGACY_UNCLAIMED'):
        with tenant.db.engine.begin() as c:
            c.execute(text('INSERT INTO cos_v6.workspaces(name,state) VALUES (\'unclaimed\',:s)'), {'s': state})
    with tenant.engines['owner'].connect() as c:
        assert set(c.execute(text('SELECT id FROM cos_v6.workspaces')).scalars()) == {tenant.w}
    with pytest.raises(DBAPIError):
        with tenant.db.engine.begin() as c:
            c.execute(text("INSERT INTO cos_v6.workspaces(name,state) VALUES ('bad','ACTIVE')"))


def test_identity_uniqueness_and_active_owner_proof(tenant):
    t = tenant
    with pytest.raises(DBAPIError):
        with t.db.engine.begin() as c:
            c.execute(text('INSERT INTO cos_v6.user_identities(user_id,issuer,subject,authenticated_at) SELECT user_id,issuer,subject,authenticated_at FROM cos_v6.user_identities LIMIT 1'))
    with pytest.raises(DBAPIError, match='invalid active owner'):
        with t.db.engine.begin() as c:
            c.execute(text('DELETE FROM cos_v6.user_identities WHERE user_id=(SELECT user_id FROM cos_v6.workspace_memberships WHERE id=:m)'), {'m': t.members['owner']})


def test_roles_and_owner_authority_are_not_grantable(tenant):
    t = tenant
    for roles in (['owner'], ['admin', 'admin']):
        with pytest.raises(DBAPIError):
            invoke(t, 'set_membership', t.w, t.members['admin'], roles, True, 'attempt escalation', actor='admin')
    with pytest.raises(DBAPIError, match='invalid active owner'):
        invoke(t, 'set_membership', t.w, t.members['owner'], [], False, 'cannot revoke current owner')
    with pytest.raises(DBAPIError, match='forbidden'):
        invoke(t, 'set_budget', t.w, None, 'USD', 1, 'not admin', actor='editor')
    with pytest.raises(DBAPIError, match='forbidden'):
        invoke(t, 'enqueue', t.w, t.b, uuid4(), b'x'*32, actor='viewer')
    invoke(t, 'set_brand_grant', t.w, t.b, t.members['admin'], True, False, 'explicit brand grant')
    invoke(t, 'enqueue', t.w, t.b, uuid4(), b'x'*32, actor='admin')
    assert scalar(t, "SELECT count(*) FROM cos_v6.audit_logs WHERE workspace_id=:w") >= 3


def test_cross_workspace_brand_and_step_references_rejected(tenant):
    t = tenant
    other = uuid4()
    with t.db.engine.begin() as c:
        c.execute(text('INSERT INTO cos_v6.workspaces(id,name) VALUES (:w,\'other\')'), {'w': other})
    with pytest.raises(DBAPIError):
        with t.db.engine.begin() as c:
            c.execute(text("INSERT INTO cos_v6.brand_grants(workspace_id,brand_id,membership_id,granted_by_membership_id,state) VALUES (:w,:b,:m,:m,'ACTIVE')"), {'w': other, 'b': t.b, 'm': t.members['owner']})
    j = job(t)
    with pytest.raises(DBAPIError):
        with t.db.engine.begin() as c:
            c.execute(text("INSERT INTO cos_v6.job_steps(workspace_id,brand_id,job_id,step_key) VALUES (:w,:b,:j,'wrong-brand')"), {'w': t.w, 'b': t.other_b, 'j': j})
    with pytest.raises(DBAPIError, match='forbidden'):
        invoke(t, 'enqueue', other, t.b, uuid4(), b'x'*32)


def test_worker_cannot_use_another_originating_actor(tenant):
    t = tenant
    job(t, actor='editor')
    assert invoke(t, 'claim', t.w, t.b, uuid4(), 30) == []
    s = claim(t, actor='editor')
    with pytest.raises(DBAPIError, match='not original actor'):
        invoke(t, 'reserve', *args(t, s), 'USD', 1)
    invoke(t, 'set_brand_grant', t.w, t.b, t.members['editor'], False, False, 'revocation')
    with pytest.raises(DBAPIError, match='forbidden'):
        invoke(t, 'reserve', *args(t, s), 'USD', 1, actor='editor')


def test_zero_cap_missing_cap_and_integer_only(tenant):
    t = tenant
    j = job(t, cap=0)
    s = claim(t)
    with pytest.raises(DBAPIError, match='BUDGET_EXCEEDED'):
        invoke(t, 'reserve', *args(t, s), 'USD', 1)
    with pytest.raises(DBAPIError):
        invoke(t, 'reserve', *args(t, s), 'USD', 0.5)
    with pytest.raises(DBAPIError, match='BUDGET_MISSING'):
        invoke(t, 'reserve', *args(t, s), 'EUR', 0)
    assert scalar(t, 'SELECT count(*) FROM cos_v6.budget_reservations WHERE workspace_id=:w') == 0


def test_two_connections_contend_for_remaining_cap(tenant):
    t = tenant
    job(t, cap=100)
    job(t, cap=100)
    s1, s2 = claim(t), claim(t)
    barrier = threading.Barrier(2)
    def reserve(s):
        with t.engines['owner'].connect() as c:
            pid = c.execute(text('SELECT pg_backend_pid()')).scalar_one()
            c.commit()
            barrier.wait(timeout=10)
            try:
                with c.begin():
                    call(c, 'reserve', *args(t, s), 'USD', 70).all()
                return pid, 'reserved'
            except DBAPIError as e:
                assert 'BUDGET_EXCEEDED' in str(e)
                return pid, 'blocked'
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(reserve, (s1, s2)))
    assert results[0][0] != results[1][0]
    assert sorted(r[1] for r in results) == ['blocked', 'reserved']
    assert scalar(t, "SELECT reserved_micros FROM cos_v6.budget_accounts WHERE workspace_id=:w AND scope='WORKSPACE'") == 70


def test_reserve_replay_release_exactly_once(tenant):
    t = tenant
    job(t)
    s = claim(t)
    r1 = invoke(t, 'reserve', *args(t, s), 'USD', 60)
    assert invoke(t, 'reserve', *args(t, s), 'USD', 60) == r1
    with pytest.raises(DBAPIError, match='replay mismatch'):
        invoke(t, 'reserve', *args(t, s), 'USD', 61)
    invoke(t, 'release_reservation', *args(t, s))
    invoke(t, 'release_reservation', *args(t, s))
    assert scalar(t, "SELECT reserved_micros FROM cos_v6.budget_accounts WHERE workspace_id=:w AND scope='WORKSPACE'") == 0
    assert scalar(t, 'SELECT count(*) FROM cos_v6.usage_ledger WHERE workspace_id=:w') == 0
    with pytest.raises(DBAPIError, match='terminal reservation conflict'):
        invoke(t, 'complete', *args(t, s), 40)


def test_settle_and_duplicate_inbox_exactly_once(tenant):
    t = tenant
    job(t)
    s = claim(t)
    invoke(t, 'reserve', *args(t, s), 'USD', 60)
    invoke(t, 'record_intent', *args(t, s))
    assert invoke(t, 'consume', *args(t, s), 'event-1', b'h'*32, 41)[0]['consume'] is True
    assert invoke(t, 'consume', *args(t, s), 'event-1', b'h'*32, 41)[0]['consume'] is False
    with pytest.raises(DBAPIError, match='inbox replay mismatch'):
        invoke(t, 'consume', *args(t, s), 'event-1', b'i'*32, 41)
    assert scalar(t, 'SELECT sum(amount_units) FROM cos_v6.usage_ledger WHERE workspace_id=:w') == 41
    assert scalar(t, 'SELECT count(*) FROM cos_v6.event_outbox WHERE workspace_id=:w') == 1
    assert scalar(t, "SELECT reserved_micros+settled_micros FROM cos_v6.budget_accounts WHERE workspace_id=:w AND scope='WORKSPACE'") == 41
    with pytest.raises(DBAPIError, match='stale fence'):
        invoke(t, 'complete', *args(t, s), 41)


def test_truthful_simulated_overrun_blocks_new_reservations(tenant):
    t = tenant
    job(t)
    s = claim(t)
    invoke(t, 'reserve', *args(t, s), 'USD', 80)
    invoke(t, 'complete', *args(t, s), 120)
    assert scalar(t, 'SELECT amount_units FROM cos_v6.usage_ledger WHERE workspace_id=:w') == 120
    assert scalar(t, "SELECT blocked FROM cos_v6.budget_accounts WHERE workspace_id=:w AND scope='WORKSPACE'") is True
    job(t)
    s2 = claim(t)
    with pytest.raises(DBAPIError, match='BUDGET_EXCEEDED'):
        invoke(t, 'reserve', *args(t, s2), 'USD', 1)


def test_skip_locked_claim_skips_locked_step(tenant):
    t = tenant
    j1, j2 = job(t), job(t)
    with t.db.engine.begin() as locked:
        sid = locked.execute(text('SELECT id FROM cos_v6.job_steps WHERE job_id=:j FOR UPDATE'), {'j': j1}).scalar_one()
        s = claim(t)
        assert s['id'] != sid and s['job_id'] == j2
    other = claim(t)
    assert other['id'] == sid
    assert invoke(t, 'claim', t.w, t.b, uuid4(), 30) == []


def test_expired_fence_cannot_write_outcome_ledger_or_outbox(tenant):
    t = tenant
    job(t)
    s = claim(t, seconds=1)
    invoke(t, 'reserve', *args(t, s), 'USD', 10)
    time.sleep(1.1)
    for routine, extra in [('complete', (5,)), ('record_intent', ()), ('heartbeat', (30,))]:
        with pytest.raises(DBAPIError, match='stale fence'):
            invoke(t, routine, *args(t, s), *extra)
    assert scalar(t, 'SELECT count(*) FROM cos_v6.usage_ledger WHERE workspace_id=:w') == 0
    assert scalar(t, 'SELECT count(*) FROM cos_v6.event_outbox WHERE workspace_id=:w') == 0
    invoke(t, 'recover', t.w, t.b)
    newer = claim(t)
    assert newer['fencing_token'] > s['fencing_token']
    with pytest.raises(DBAPIError, match='stale fence'):
        invoke(t, 'complete', *args(t, s), 5)
    invoke(t, 'complete', *args(t, newer), 5)


def test_process_death_after_committed_intent_recovers_no_blind_retry(tenant):
    t = tenant
    job(t)
    code = '''import os,sys
from uuid import UUID,uuid4
from sqlalchemy import create_engine
from foundation.service import call
engine=create_engine(sys.argv[1]); w=UUID(sys.argv[2]); b=UUID(sys.argv[3])
with engine.begin() as c:
 s=call(c,'claim',w,b,uuid4(),1).mappings().one()
 a=(w,s['id'],s['lease_owner'],s['fencing_token'])
 call(c,'reserve',*a,'USD',60).all()
 call(c,'record_intent',*a).all()
os._exit(23)
'''
    env = {k: os.environ[k] for k in ('PATH', 'HOME', 'PYTHONPATH', 'PYTHON_DOTENV_DISABLED') if k in os.environ}
    p = subprocess.run([sys.executable, '-c', code, t.engines['owner'].url.render_as_string(hide_password=False), str(t.w), str(t.b)], env=env, capture_output=True, text=True)
    assert p.returncode == 23, p.stderr
    time.sleep(1.1)
    fresh = create_engine(t.engines['owner'].url)
    with fresh.begin() as c:
        assert call(c, 'recover', t.w, t.b).scalar_one() == 1
        assert call(c, 'claim', t.w, t.b, uuid4(), 30).all() == []
    fresh.dispose()
    assert scalar(t, 'SELECT status FROM cos_v6.job_steps WHERE workspace_id=:w') == 'RECONCILING'
    assert scalar(t, 'SELECT submission_count FROM cos_v6.job_steps WHERE workspace_id=:w') == 1
    assert scalar(t, 'SELECT state FROM cos_v6.budget_reservations WHERE workspace_id=:w') == 'RESERVED'
    assert scalar(t, "SELECT type FROM cos_v6.event_outbox WHERE workspace_id=:w") == 'job.reconciling'


def test_intent_cannot_release_or_resubmit(tenant):
    t = tenant
    job(t)
    s = claim(t)
    invoke(t, 'reserve', *args(t, s), 'USD', 60)
    invoke(t, 'record_intent', *args(t, s))
    with pytest.raises(DBAPIError, match='retains reservation'):
        invoke(t, 'release_reservation', *args(t, s))
    with pytest.raises(DBAPIError, match='never blind resubmit'):
        invoke(t, 'record_intent', *args(t, s))


def test_outbox_lease_expiry_fences_ack_and_reclaims(tenant):
    t = tenant
    job(t)
    s = claim(t)
    invoke(t, 'reserve', *args(t, s), 'USD', 5)
    invoke(t, 'complete', *args(t, s), 5)
    worker = uuid4()
    e = invoke(t, 'claim_event', t.w, worker, 1)[0]
    assert invoke(t, 'claim_event', t.w, uuid4(), 30) == []
    time.sleep(1.1)
    with pytest.raises(DBAPIError, match='stale event fence'):
        invoke(t, 'ack_event', t.w, e['event_id'], worker, e['fencing_token'])
    newer = invoke(t, 'claim_event', t.w, uuid4(), 30)[0]
    assert newer['fencing_token'] > e['fencing_token']
    invoke(t, 'ack_event', t.w, newer['event_id'], newer['lease_owner'], newer['fencing_token'])
    assert scalar(t, 'SELECT state FROM cos_v6.event_outbox WHERE workspace_id=:w') == 'DELIVERED'


def test_mode_cannot_be_live_and_publication_unimplemented(tenant):
    t = tenant
    job(t)
    with pytest.raises(DBAPIError):
        with t.db.engine.begin() as c:
            c.execute(text("UPDATE cos_v6.production_jobs SET execution_mode='LIVE' WHERE workspace_id=:w"), {'w': t.w})
    with pytest.raises(ValueError):
        with t.engines['owner'].begin() as c:
            call(c, 'dispatch_live', t.w)
    assert scalar(t, "SELECT to_regclass('cos_v6.publications') IS NULL") is True


def test_idempotency_replay_and_different_hash_conflict(tenant):
    t = tenant
    op = uuid4()
    j = invoke(t, 'enqueue', t.w, t.b, op, b'x'*32)
    assert invoke(t, 'enqueue', t.w, t.b, op, b'x'*32) == j
    with pytest.raises(DBAPIError, match='idempotency conflict'):
        invoke(t, 'enqueue', t.w, t.b, op, b'y'*32)


def test_null_fence_is_not_a_bypass(tenant):
    t = tenant
    job(t)
    s = claim(t)
    with pytest.raises(DBAPIError, match='stale fence'):
        invoke(t, 'reserve', t.w, s['id'], s['lease_owner'], None, 'USD', 10)
    assert scalar(t, 'SELECT count(*) FROM cos_v6.budget_reservations WHERE workspace_id=:w') == 0


def test_inbox_failure_rolls_back_business_ledger_and_outbox(tenant):
    t = tenant
    job(t)
    s = claim(t)
    invoke(t, 'reserve', *args(t, s), 'USD', 10)
    with pytest.raises(DBAPIError):
        invoke(t, 'consume', *args(t, s), 'invalid-hash', b'bad', 5)
    for table in ('usage_ledger', 'event_inbox', 'event_outbox'):
        assert scalar(t, f'SELECT count(*) FROM cos_v6.{table} WHERE workspace_id=:w') == 0
    assert scalar(t, 'SELECT state FROM cos_v6.budget_reservations WHERE workspace_id=:w') == 'RESERVED'
    assert scalar(t, 'SELECT status FROM cos_v6.job_steps WHERE workspace_id=:w') == 'RUNNING'


def test_concurrent_duplicate_inbox_has_one_effect(tenant):
    t = tenant
    job(t)
    s = claim(t)
    invoke(t, 'reserve', *args(t, s), 'USD', 10)
    barrier = threading.Barrier(2)
    def consume(_):
        with t.engines['owner'].begin() as c:
            barrier.wait(timeout=10)
            return call(c, 'consume', *args(t, s), 'same-event', b'h'*32, 5).scalar_one()
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(consume, range(2))) == [False, True]
    for table in ('usage_ledger', 'event_inbox', 'event_outbox'):
        assert scalar(t, f'SELECT count(*) FROM cos_v6.{table} WHERE workspace_id=:w') == 1


def test_settle_release_race_is_one_terminal_outcome(tenant):
    t = tenant
    job(t)
    s = claim(t)
    invoke(t, 'reserve', *args(t, s), 'USD', 10)
    barrier = threading.Barrier(2)
    def terminal(routine):
        with t.engines['owner'].connect() as c:
            barrier.wait(timeout=10)
            try:
                with c.begin():
                    call(c, routine, *args(t, s), *((5,) if routine == 'complete' else ())).all()
                return 'ok'
            except DBAPIError as e:
                assert 'stale fence' in str(e) or 'terminal reservation conflict' in str(e)
                return 'conflict'
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(terminal, ('complete', 'release_reservation'))) == ['conflict', 'ok']
    assert scalar(t, 'SELECT state FROM cos_v6.budget_reservations WHERE workspace_id=:w') in ('SETTLED', 'RELEASED')
    assert scalar(t, 'SELECT count(*) FROM cos_v6.usage_ledger WHERE workspace_id=:w') <= 1


def test_immutable_history_and_counter_rebuild(tenant):
    t = tenant
    job(t)
    s = claim(t)
    invoke(t, 'reserve', *args(t, s), 'USD', 10)
    invoke(t, 'complete', *args(t, s), 5)
    for table in ('usage_ledger', 'usage_allocations', 'reservation_allocations', 'audit_logs', 'job_transitions', 'event_outbox'):
        with pytest.raises(DBAPIError, match='immutable history'):
            with t.db.engine.begin() as c:
                c.execute(text(f'DELETE FROM cos_v6.{table} WHERE workspace_id=:w'), {'w': t.w})
    assert scalar(t, 'SELECT count(*) FROM cos_v6.job_transitions WHERE workspace_id=:w') == 3
    assert scalar(t, '''SELECT count(*) FROM cos_v6.budget_accounts b WHERE b.workspace_id=:w
        AND b.settled_micros=(SELECT coalesce(sum(a.amount_micros),0) FROM cos_v6.usage_allocations a WHERE a.budget_account_id=b.id)
        AND b.reserved_micros=(SELECT coalesce(sum(a.amount_micros),0) FROM cos_v6.reservation_allocations a JOIN cos_v6.budget_reservations r ON (r.workspace_id,r.id)=(a.workspace_id,a.reservation_id) WHERE a.budget_account_id=b.id AND r.state='RESERVED')''') == 2


def test_downgrade_preserves_new_ledger_history(tenant):
    t = tenant
    job(t)
    s = claim(t)
    invoke(t, 'reserve', *args(t, s), 'USD', 10)
    invoke(t, 'complete', *args(t, s), 5)
    with pytest.raises(RuntimeError, match='Retention-safe'):
        with t.db.engine.begin() as c:
            migrate(c, 'downgrade')
    assert scalar(t, 'SELECT amount_units FROM cos_v6.usage_ledger WHERE workspace_id=:w') == 5
    assert scalar(t, 'SELECT count(*) FROM cos_v6.event_outbox WHERE workspace_id=:w') == 1


def test_bigint_cap_comparison_does_not_overflow(tenant):
    t = tenant
    maximum = 9223372036854775807
    job(t, amount=maximum, cap=maximum)
    job(t, amount=maximum, cap=maximum)
    s1, s2 = claim(t), claim(t)
    invoke(t, 'reserve', *args(t, s1), 'USD', maximum)
    with pytest.raises(DBAPIError, match='BUDGET_EXCEEDED'):
        invoke(t, 'reserve', *args(t, s2), 'USD', 1)
    assert scalar(t, "SELECT reserved_micros FROM cos_v6.budget_accounts WHERE workspace_id=:w AND scope='WORKSPACE'") == maximum
