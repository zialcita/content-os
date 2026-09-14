"""Exact identity privilege acceptance audit, callable by revision and global hooks."""
from sqlalchemy import text

RUNTIME_FUNCTIONS = frozenset({
    'api_bind(text,text,boolean)', 'api_actor()', 'api_allowed(uuid,uuid,text)',
    'api_authorize(uuid,uuid,text)', 'api_session()', 'api_logout()', 'api_switch(uuid)',
    'api_onboarding(text,text)', 'api_create_workspace(uuid,text,text)',
    'api_read(text,uuid,uuid)', 'api_list(text,uuid,uuid,timestamp with time zone,uuid,integer)',
    'api_write_brand(uuid,uuid,text,text,bigint,text,bytea)',
    'api_edit_member(uuid,uuid,text[],boolean,bigint)',
    'api_grant(uuid,uuid,uuid,boolean,boolean,bigint)',
    'api_invite(uuid,text,text,text[],uuid[],bytea)', 'api_accept_invite(text)',
    'api_revoke_invite(uuid,uuid,bigint)',
})
AUTH_FUNCTIONS = frozenset({
    'auth_start(bytea,bytea,text,text,text,text,bytea)',
    'auth_consume(bytea,bytea)', 'auth_finalize(uuid,text,text,text,text,bytea,bytea)',
})
INTERNAL_FUNCTIONS = frozenset({'api_require_write()', 'api_workspace_json(uuid)',
    'api_brand_json(uuid)', 'api_member_json(uuid)', 'api_invitation_json(uuid)'})
IDENTITY_FUNCTIONS = RUNTIME_FUNCTIONS | AUTH_FUNCTIONS | INTERNAL_FUNCTIONS
RUNTIME_TABLES = frozenset({'workspaces', 'workspace_memberships', 'brands', 'brand_grants'})
PRIVATE_TABLES = frozenset({'sessions', 'login_transactions', 'identity_profiles',
                          'onboarding_authorizations', 'invitations', 'invitation_brands', 'identity_replays'})


def audit_identity_privileges(connection):
    """Raise on effective privilege drift, insecure roles or unsafe definer settings.

    Does not alter foundation grants, global defaults or install a global env hook.
    Deployment logins must only inherit the appropriate one of these runtime groups.
    """
    failures = []
    for role, expected in [('cos_api_runtime', RUNTIME_FUNCTIONS), ('cos_identity_auth', AUTH_FUNCTIONS),
                           ('cos_identity_owner', IDENTITY_FUNCTIONS)]:
        rows = connection.execute(text('''
            SELECT p.proname||'('||replace(oidvectortypes(p.proargtypes),', ',',')||')' AS signature,
            has_function_privilege(:role,p.oid,'EXECUTE') AS allowed,
            EXISTS(SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
                   WHERE a.grantee=0 AND a.privilege_type='EXECUTE') AS public_execute,
            p.prosecdef,p.proconfig,pg_get_userbyid(p.proowner) AS owner
            FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='cos_v6'
        '''), {'role': role}).mappings().all()
        if connection.execute(text("SELECT has_schema_privilege(:r,'cos_v6','CREATE')"), {'r': role}).scalar_one():
            failures.append(role + ' may create schema objects')
        actual = {r['signature'] for r in rows if r['allowed']}
        if actual != expected:
            failures.append(f'{role} function allowlist drift: extra={sorted(actual-expected)} missing={sorted(expected-actual)}')
        for r in rows:
            if r['public_execute']:
                failures.append('PUBLIC EXECUTE: ' + r['signature'])
            if r['signature'] in IDENTITY_FUNCTIONS and (
                    not r['prosecdef'] or r['owner'] != 'cos_identity_owner' or
                    r['proconfig'] != ['search_path=pg_catalog, cos_v6']):
                failures.append('unsafe identity definer: ' + r['signature'])
        tables = connection.execute(text('''
            SELECT c.relname,has_any_column_privilege(:role,c.oid,'SELECT') AS can_read,
                   (has_table_privilege(:role,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
                    OR has_any_column_privilege(:role,c.oid,'INSERT,UPDATE,REFERENCES')) AS can_write,
                   c.relrowsecurity,c.relforcerowsecurity
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='cos_v6' AND c.relkind IN ('r','p')
        '''), {'role': role}).mappings().all()
        reads = {t['relname'] for t in tables if t['can_read']}
        owner_read = PRIVATE_TABLES | RUNTIME_TABLES | {'users', 'user_identities'}
        expected_read = owner_read if role == 'cos_identity_owner' else RUNTIME_TABLES if role == 'cos_api_runtime' else frozenset()
        if reads != expected_read:
            failures.append(role + ' table read allowlist drift')
        if role == 'cos_identity_owner':
            expected_by_permission = {'INSERT': owner_read | {'audit_logs'}, 'UPDATE': owner_read,
                                      'DELETE': PRIVATE_TABLES, 'TRUNCATE': set(), 'REFERENCES': set(), 'TRIGGER': set()}
            for permission, allowed_tables in expected_by_permission.items():
                granted = set(connection.execute(text('''SELECT c.relname FROM pg_class c
                    JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='cos_v6' AND c.relkind IN ('r','p')
                    AND (has_table_privilege(:r,c.oid,:p) OR CASE WHEN :p IN ('INSERT','UPDATE','REFERENCES')
                         THEN has_any_column_privilege(:r,c.oid,:p) ELSE false END)'''), {'r': role, 'p': permission}).scalars())
                if granted != allowed_tables:
                    failures.append('cos_identity_owner ' + permission + ' allowlist drift')
        for t in tables:
            if role != 'cos_identity_owner' and t['can_write']:
                failures.append(role + ' sensitive table DML: ' + t['relname'])
            if t['relname'] in PRIVATE_TABLES and not (t['relrowsecurity'] and t['relforcerowsecurity']):
                failures.append('private table RLS not forced: ' + t['relname'])
            if t['relname'] in RUNTIME_TABLES and not t['relrowsecurity']:
                failures.append('runtime table RLS disabled: ' + t['relname'])
    roles = connection.execute(text('''SELECT rolname,rolsuper,rolbypassrls,rolcreaterole,rolcreatedb,rolcanlogin
        FROM pg_roles WHERE rolname IN ('cos_api_runtime','cos_identity_auth','cos_identity_owner')''')).mappings().all()
    if len(roles) != 3:
        failures.append('identity roles missing')
    for r in roles:
        if any(r[k] for k in ('rolsuper', 'rolbypassrls', 'rolcreaterole', 'rolcreatedb', 'rolcanlogin')):
            failures.append('unsafe role attributes: ' + r['rolname'])
    if connection.execute(text('''SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member
        WHERE r.rolname IN ('cos_api_runtime','cos_identity_auth','cos_identity_owner')''')).scalar_one():
        failures.append('identity role inherits unexpected role')
    if failures:
        raise RuntimeError('Identity privilege audit failed: ' + '; '.join(sorted(set(failures))))
