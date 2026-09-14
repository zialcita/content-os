"""Migration acceptance audit, not runtime security or a default-ACL guarantee.

Future revisions must explicitly revoke PUBLIC EXECUTE on new routines and review
any runtime allowlist expansion. Never change the administrator's global defaults.
"""
from sqlalchemy import text

# Exact signatures: adding an overload must not silently expand runtime authority.
RUNTIME_FUNCTIONS = frozenset({
    'actor()', 'allowed(uuid,uuid,text)',
    'set_membership(uuid,uuid,text[],boolean,text)',
    'set_brand_grant(uuid,uuid,uuid,boolean,boolean,text)',
    'set_budget(uuid,uuid,text,bigint,text)', 'enqueue(uuid,uuid,uuid,bytea)',
    'claim(uuid,uuid,uuid,integer)', 'heartbeat(uuid,uuid,uuid,bigint,integer)',
    'reserve(uuid,uuid,uuid,bigint,text,bigint)',
    'release_reservation(uuid,uuid,uuid,bigint)',
    'record_intent(uuid,uuid,uuid,bigint)', 'complete(uuid,uuid,uuid,bigint,bigint)',
    'consume(uuid,uuid,uuid,bigint,text,bytea,bigint)', 'recover(uuid,uuid)',
    'claim_event(uuid,uuid,integer)', 'ack_event(uuid,uuid,uuid,bigint)',
})


def audit_function_privileges(connection):
    """Fail acceptance on PUBLIC execute or any runtime allowlist mismatch.

    Run inside the migration transaction after each revision and on head reruns.
    acldefault is essential: NULL proacl includes implicit global PUBLIC EXECUTE.
    All cos_v6 routines are audited, not merely the initial revision's functions.
    """
    rows = connection.execute(text('''
        SELECT p.proname || '(' || replace(oidvectortypes(p.proargtypes), ', ', ',') || ')' AS signature,
               EXISTS (SELECT 1 FROM aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a
                       WHERE a.grantee=0 AND a.privilege_type='EXECUTE') AS public_execute,
               has_function_privilege('cos_foundation_runtime', p.oid, 'EXECUTE') AS runtime_execute
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='cos_v6'
        ORDER BY signature
    ''')).mappings().all()
    public = [r['signature'] for r in rows if r['public_execute']]
    runtime = {r['signature'] for r in rows if r['runtime_execute']}
    unexpected = sorted(runtime - RUNTIME_FUNCTIONS)
    missing = sorted(RUNTIME_FUNCTIONS - runtime)
    if public or unexpected or missing:
        raise RuntimeError(f'Foundation function privilege audit failed: PUBLIC EXECUTE={public}; '
                           f'unallowlisted runtime={unexpected}; missing runtime={missing}')
