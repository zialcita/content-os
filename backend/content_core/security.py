"""Explicit grants for the private local-upload module; never a wildcard grant."""
from sqlalchemy import text

RUNTIME_FUNCTIONS=frozenset({
 'cc_read(uuid,uuid,text,uuid)','cc_create_upload(uuid,uuid,text,text,bigint,bytea,text,text)',
 'cc_transfer(uuid,uuid,uuid,integer)','cc_record_part(uuid,uuid,uuid,integer,integer,bytea,bigint)',
 'cc_finalize(uuid,uuid,uuid,uuid,bigint,text)','cc_cancel(uuid,uuid,uuid,bigint)',
 'cc_revise(uuid,uuid,uuid,text,text,bigint,text)','cc_download(uuid,uuid,uuid,uuid)'})
WORKER_FUNCTIONS=frozenset({'cc_claim(uuid,uuid)','cc_heartbeat(uuid,uuid,uuid,text,bigint)',
 'cc_finish(uuid,uuid,uuid,text,bigint,text,bytea,bigint,text,text,text)'})
INTERNAL_FUNCTIONS=frozenset({'cc_immutable()','cc_registry_guard()','cc_child_guard()',
 'cc_snapshot(uuid)','cc_total_integrity()','cc_graph_lock(uuid,uuid)',
 'cc_construct(uuid,uuid,uuid,uuid,uuid,text,text,uuid,text)','cc_upload_json(uuid)',
 'cc_job_json(uuid)','cc_worker_authorized(uuid,uuid,uuid)','cc_fenced(uuid,uuid,uuid,text,bigint)'})
ALL_FUNCTIONS=RUNTIME_FUNCTIONS|WORKER_FUNCTIONS|INTERNAL_FUNCTIONS
TABLES=frozenset({'content_capacity','brand_graph_locks','source_assets','upload_intents','upload_parts',
 'ingestion_jobs','ingestion_events','content_replays','version_registry','source_versions',
 'source_validation_results','dependency_edges'})
IDENTITY_READS=frozenset({'workspaces','workspace_memberships','brands','brand_grants','users','user_identities'})


def audit_content_privileges(c):
    for role, expected in [('cos_content_worker',WORKER_FUNCTIONS),
                           ('cos_content_owner',ALL_FUNCTIONS|{'api_actor()','api_authorize(uuid,uuid,text)'})]:
        row=c.execute(text('SELECT rolsuper,rolbypassrls,rolcanlogin,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=:r'),{'r':role}).one()
        if any(row): raise RuntimeError('Unsafe content role attributes')
        if c.execute(text('SELECT count(*) FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member WHERE r.rolname=:r'),{'r':role}).scalar_one():
            raise RuntimeError('Content group role must not inherit authority')
        if c.execute(text("SELECT has_schema_privilege(:r,'cos_v6','CREATE')"),{'r':role}).scalar_one():
            raise RuntimeError('Content schema CREATE forbidden')
        rows=c.execute(text("""SELECT p.proname||'('||replace(oidvectortypes(p.proargtypes),', ',',')||')' signature,
          has_function_privilege(:r,p.oid,'EXECUTE') allowed,p.prosecdef,p.proconfig,pg_get_userbyid(p.proowner) owner,
          EXISTS(SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE a.grantee=0 AND a.privilege_type='EXECUTE') public
          FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='cos_v6'"""),{'r':role}).mappings().all()
        if {r['signature'] for r in rows if r['allowed']}!=expected: raise RuntimeError('Content function allowlist drift')
        for row in rows:
            if row['public']: raise RuntimeError('PUBLIC function access forbidden')
            if row['signature'] in ALL_FUNCTIONS and (not row['prosecdef'] or row['owner']!='cos_content_owner' or row['proconfig']!=['search_path=pg_catalog, cos_v6']):
                raise RuntimeError('Content definer drift')
        tables=c.execute(text("""SELECT relname,relrowsecurity,relforcerowsecurity,
           has_any_column_privilege(:r,c.oid,'SELECT') rd,
           (has_table_privilege(:r,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') OR has_any_column_privilege(:r,c.oid,'INSERT,UPDATE,REFERENCES')) wr
           FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='cos_v6' AND relkind='r'"""),{'r':role}).mappings().all()
        expected_reads=TABLES|IDENTITY_READS if role=='cos_content_owner' else frozenset()
        if {r['relname'] for r in tables if r['rd']}!=expected_reads: raise RuntimeError('Content read grant drift')
        for row in tables:
            if row['relname'] in TABLES and not (row['relrowsecurity'] and row['relforcerowsecurity']): raise RuntimeError('Content RLS not forced')
            if row['wr'] and (role!='cos_content_owner' or row['relname'] not in TABLES|{'workspaces'}): raise RuntimeError('Content write grant drift')
        if role=='cos_content_owner':
            for perm in ('INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER'):
                expected_tables=TABLES if perm in ('INSERT','UPDATE') else frozenset()
                found=set(c.execute(text("SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='cos_v6' AND relkind='r' AND has_table_privilege(:r,c.oid,:p)"),{'r':role,'p':perm}).scalars())
                if found!=expected_tables: raise RuntimeError('Content exact table permission drift')
            columns=set(c.execute(text("SELECT column_name FROM information_schema.column_privileges WHERE grantee='cos_content_owner' AND table_schema='cos_v6' AND table_name='workspaces' AND privilege_type='UPDATE'")).scalars())
            if columns!={'id'}: raise RuntimeError('Content workspace column privilege drift')


def guard_worker(engine):
    if engine.echo or not engine.hide_parameters: raise RuntimeError('Worker parameters must be hidden')
    with engine.connect() as c:
        row=c.execute(text("SELECT rolsuper,rolbypassrls,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user")).one()
        if any(row): raise RuntimeError('Privileged worker login refused')
        if c.execute(text("SELECT has_schema_privilege(current_user,'cos_v6','CREATE')")).scalar_one():
            raise RuntimeError('Worker schema creation forbidden')
        actual=set(c.execute(text("SELECT p.proname||'('||replace(oidvectortypes(proargtypes),', ',',')||')' FROM pg_proc p JOIN pg_namespace n ON n.oid=pronamespace WHERE n.nspname='cos_v6' AND has_function_privilege(current_user,p.oid,'EXECUTE')")).scalars())
        if actual!=WORKER_FUNCTIONS: raise RuntimeError('Worker function authority mismatch')
        leaked=c.execute(text("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='cos_v6' AND relkind='r' AND (has_any_column_privilege(current_user,c.oid,'SELECT,INSERT,UPDATE,REFERENCES') OR has_table_privilege(current_user,c.oid,'DELETE,TRUNCATE,TRIGGER'))")).scalar_one()
        if leaked: raise RuntimeError('Worker direct data authority forbidden')
