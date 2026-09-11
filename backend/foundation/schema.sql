-- M1 bounded local simulation foundation. No provider dispatch exists.
CREATE SCHEMA cos_v6;
CREATE ROLE cos_foundation_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
REVOKE ALL ON SCHEMA cos_v6 FROM PUBLIC;
GRANT USAGE ON SCHEMA cos_v6 TO cos_foundation_runtime;
CREATE TABLE cos_v6.users (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), display_name text NOT NULL,
 status text NOT NULL CHECK(status IN ('ACTIVE','UNCLAIMED','SUSPENDED')),
 verified_at timestamptz, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(status <> 'ACTIVE' OR verified_at IS NOT NULL));
CREATE TABLE cos_v6.user_identities (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES cos_v6.users,
 issuer text NOT NULL CHECK(length(issuer)>0), subject text NOT NULL CHECK(length(subject)>0),
 authenticated_at timestamptz NOT NULL, UNIQUE(issuer,subject));
-- Privileged provisioning only; not OIDC verification. Never trust custom GUC actor IDs.
CREATE TABLE cos_v6.database_principals (
 database_role name PRIMARY KEY, user_id uuid NOT NULL REFERENCES cos_v6.users);
CREATE TABLE cos_v6.workspaces (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL, timezone text NOT NULL DEFAULT 'UTC',
 state text NOT NULL DEFAULT 'PENDING_ONBOARDING' CHECK(state IN ('PENDING_ONBOARDING','LEGACY_UNCLAIMED','ACTIVE','SUSPENDED')),
 owner_membership_id uuid, auth_epoch bigint NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK(state <> 'ACTIVE' OR owner_membership_id IS NOT NULL));
CREATE TABLE cos_v6.workspace_memberships (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES cos_v6.workspaces,
 user_id uuid NOT NULL REFERENCES cos_v6.users, roles text[] NOT NULL DEFAULT '{}',
 state text NOT NULL CHECK(state IN ('ACTIVE','PENDING_VERIFICATION','REVOKED')),
 verified_at timestamptz, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id), UNIQUE(workspace_id,user_id),
 CHECK(roles <@ ARRAY['admin','editor','reviewer','publisher','viewer']::text[]),
 CHECK(array_position(roles,NULL) IS NULL), CHECK(state <> 'ACTIVE' OR verified_at IS NOT NULL));
ALTER TABLE cos_v6.workspaces ADD CONSTRAINT owner_membership_fk FOREIGN KEY(id,owner_membership_id)
 REFERENCES cos_v6.workspace_memberships(workspace_id,id) DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE cos_v6.brands (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES cos_v6.workspaces,
 name text NOT NULL, state text NOT NULL DEFAULT 'ACTIVE' CHECK(state IN ('ACTIVE','SUSPENDED')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), UNIQUE(workspace_id,id));
CREATE TABLE cos_v6.brand_grants (
 workspace_id uuid NOT NULL, brand_id uuid NOT NULL, membership_id uuid NOT NULL,
 granted_by_membership_id uuid NOT NULL, state text NOT NULL CHECK(state IN ('ACTIVE','REVOKED')),
 can_connect boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,brand_id,membership_id),
 FOREIGN KEY(workspace_id,brand_id) REFERENCES cos_v6.brands(workspace_id,id),
 FOREIGN KEY(workspace_id,membership_id) REFERENCES cos_v6.workspace_memberships(workspace_id,id),
 FOREIGN KEY(workspace_id,granted_by_membership_id) REFERENCES cos_v6.workspace_memberships(workspace_id,id));
CREATE TABLE cos_v6.audit_logs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES cos_v6.workspaces,
 actor_membership_id uuid NOT NULL, action text NOT NULL, metadata jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,actor_membership_id) REFERENCES cos_v6.workspace_memberships(workspace_id,id));
CREATE TABLE cos_v6.production_jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL, brand_id uuid NOT NULL,
 requested_by_membership_id uuid NOT NULL, logical_operation_id uuid NOT NULL,
 scope_type text NOT NULL DEFAULT 'BRAND' CHECK(scope_type='BRAND'),
 purpose text NOT NULL DEFAULT 'ADMIN' CHECK(purpose='ADMIN'),
 job_kind text NOT NULL DEFAULT 'LOCAL_SIMULATION' CHECK(job_kind='LOCAL_SIMULATION'),
 originating_operation_id text NOT NULL DEFAULT 'foundationSimulation' CHECK(originating_operation_id='foundationSimulation'),
 paid_authority text NOT NULL DEFAULT 'NONE' CHECK(paid_authority='NONE'),
 execution_mode text NOT NULL DEFAULT 'SIMULATED' CHECK(execution_mode='SIMULATED'),
 input_hash bytea NOT NULL CHECK(octet_length(input_hash)=32),
 status text NOT NULL DEFAULT 'QUEUED' CHECK(status IN ('QUEUED','RUNNING','RECONCILING','SUCCEEDED')),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id), UNIQUE(workspace_id,id,brand_id), UNIQUE(workspace_id,logical_operation_id),
 FOREIGN KEY(workspace_id,brand_id) REFERENCES cos_v6.brands(workspace_id,id),
 FOREIGN KEY(workspace_id,requested_by_membership_id) REFERENCES cos_v6.workspace_memberships(workspace_id,id));
CREATE TABLE cos_v6.job_steps (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL, brand_id uuid NOT NULL, job_id uuid NOT NULL,
 step_key text NOT NULL DEFAULT 'local', status text NOT NULL DEFAULT 'QUEUED' CHECK(status IN ('QUEUED','RUNNING','RECONCILING','SUCCEEDED')),
 next_attempt_at timestamptz NOT NULL DEFAULT clock_timestamp(), lease_owner uuid, lease_expires_at timestamptz,
 heartbeat_at timestamptz, fencing_token bigint NOT NULL DEFAULT 0 CHECK(fencing_token>=0), submission_count int NOT NULL DEFAULT 0 CHECK(submission_count BETWEEN 0 AND 1),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK((lease_owner IS NULL)=(lease_expires_at IS NULL)),
 CHECK((status='RUNNING')=(lease_owner IS NOT NULL)),
 CHECK(status<>'RUNNING' OR heartbeat_at IS NOT NULL), UNIQUE(workspace_id,id), UNIQUE(workspace_id,job_id,id),
 UNIQUE(workspace_id,id,brand_id), UNIQUE(workspace_id,job_id,step_key),
 FOREIGN KEY(workspace_id,job_id,brand_id) REFERENCES cos_v6.production_jobs(workspace_id,id,brand_id));
CREATE INDEX runnable_steps ON cos_v6.job_steps(next_attempt_at,id) WHERE status='QUEUED';
CREATE INDEX expired_steps ON cos_v6.job_steps(lease_expires_at,id) WHERE status='RUNNING';
CREATE TABLE cos_v6.provider_attempts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL, job_id uuid NOT NULL, step_id uuid NOT NULL,
 execution_mode text NOT NULL DEFAULT 'SIMULATED' CHECK(execution_mode='SIMULATED'),
 provider text NOT NULL DEFAULT 'local_fixture' CHECK(provider='local_fixture'),
 claim_token bigint NOT NULL, intent_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 state text NOT NULL DEFAULT 'INTENT' CHECK(state IN ('INTENT','SUCCEEDED')),
 UNIQUE(workspace_id,step_id), FOREIGN KEY(workspace_id,job_id,step_id) REFERENCES cos_v6.job_steps(workspace_id,job_id,id));
CREATE TABLE cos_v6.budget_accounts (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES cos_v6.workspaces,
 scope text NOT NULL CHECK(scope IN ('WORKSPACE','JOB')), job_id uuid,
 execution_mode text NOT NULL DEFAULT 'SIMULATED' CHECK(execution_mode='SIMULATED'),
 currency text NOT NULL CHECK(currency ~ '^[A-Z]{3}$'), limit_micros bigint NOT NULL DEFAULT 0 CHECK(limit_micros>=0),
 reserved_micros bigint NOT NULL DEFAULT 0 CHECK(reserved_micros>=0), settled_micros bigint NOT NULL DEFAULT 0 CHECK(settled_micros>=0),
 blocked boolean NOT NULL DEFAULT false, UNIQUE(workspace_id,id),
 CHECK((scope='WORKSPACE' AND job_id IS NULL) OR (scope='JOB' AND job_id IS NOT NULL)),
 FOREIGN KEY(workspace_id,job_id) REFERENCES cos_v6.production_jobs(workspace_id,id));
CREATE UNIQUE INDEX workspace_account ON cos_v6.budget_accounts(workspace_id,currency) WHERE scope='WORKSPACE';
CREATE UNIQUE INDEX job_account ON cos_v6.budget_accounts(workspace_id,job_id,currency) WHERE scope='JOB';
CREATE TABLE cos_v6.budget_reservations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL, job_id uuid NOT NULL, step_id uuid NOT NULL,
 currency text NOT NULL CHECK(currency ~ '^[A-Z]{3}$'), reserved_micros bigint NOT NULL CHECK(reserved_micros>=0),
 execution_mode text NOT NULL DEFAULT 'SIMULATED' CHECK(execution_mode='SIMULATED'),
 state text NOT NULL DEFAULT 'RESERVED' CHECK(state IN ('RESERVED','SETTLED','RELEASED')),
 actual_micros bigint CHECK(actual_micros>=0), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id), UNIQUE(workspace_id,step_id),
 FOREIGN KEY(workspace_id,job_id,step_id) REFERENCES cos_v6.job_steps(workspace_id,job_id,id));
CREATE TABLE cos_v6.reservation_allocations (
 workspace_id uuid NOT NULL, reservation_id uuid NOT NULL, budget_account_id uuid NOT NULL, amount_micros bigint NOT NULL CHECK(amount_micros>=0),
 PRIMARY KEY(workspace_id,reservation_id,budget_account_id),
 FOREIGN KEY(workspace_id,reservation_id) REFERENCES cos_v6.budget_reservations(workspace_id,id),
 FOREIGN KEY(workspace_id,budget_account_id) REFERENCES cos_v6.budget_accounts(workspace_id,id));
CREATE TABLE cos_v6.usage_ledger (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL, reservation_id uuid NOT NULL,
 ledger_dimension text NOT NULL DEFAULT 'PROVIDER_COST' CHECK(ledger_dimension='PROVIDER_COST'),
 execution_mode text NOT NULL DEFAULT 'SIMULATED' CHECK(execution_mode='SIMULATED'),
 entry_type text NOT NULL DEFAULT 'SETTLEMENT' CHECK(entry_type='SETTLEMENT'),
 amount_units bigint NOT NULL CHECK(amount_units>=0), unit text NOT NULL DEFAULT 'micros' CHECK(unit='micros'),
 currency text NOT NULL CHECK(currency ~ '^[A-Z]{3}$'), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id), UNIQUE(workspace_id,reservation_id), FOREIGN KEY(workspace_id,reservation_id) REFERENCES cos_v6.budget_reservations(workspace_id,id));
CREATE TABLE cos_v6.usage_allocations (
 workspace_id uuid NOT NULL, usage_entry_id uuid NOT NULL, budget_account_id uuid NOT NULL, amount_micros bigint NOT NULL CHECK(amount_micros>=0),
 PRIMARY KEY(workspace_id,usage_entry_id,budget_account_id),
 FOREIGN KEY(workspace_id,usage_entry_id) REFERENCES cos_v6.usage_ledger(workspace_id,id),
 FOREIGN KEY(workspace_id,budget_account_id) REFERENCES cos_v6.budget_accounts(workspace_id,id));
CREATE TABLE cos_v6.job_transitions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL, job_id uuid NOT NULL, step_id uuid NOT NULL,
 from_state text, to_state text NOT NULL, fencing_token bigint NOT NULL,
 occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,job_id,step_id) REFERENCES cos_v6.job_steps(workspace_id,job_id,id));
CREATE TABLE cos_v6.event_outbox (
 event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL, job_id uuid NOT NULL, step_id uuid NOT NULL,
 type text NOT NULL CHECK(type IN ('job.succeeded','job.reconciling')), data jsonb NOT NULL DEFAULT '{}',
 occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(), state text NOT NULL DEFAULT 'PENDING' CHECK(state IN ('PENDING','DELIVERING','DELIVERED')),
 lease_owner uuid, lease_expires_at timestamptz, fencing_token bigint NOT NULL DEFAULT 0,
 delivery_count int NOT NULL DEFAULT 0, UNIQUE(workspace_id,step_id,type),
 CHECK((lease_owner IS NULL)=(lease_expires_at IS NULL)),
 CHECK((state='DELIVERING')=(lease_owner IS NOT NULL)),
 FOREIGN KEY(workspace_id,job_id,step_id) REFERENCES cos_v6.job_steps(workspace_id,job_id,id));
CREATE TABLE cos_v6.event_inbox (
 workspace_id uuid NOT NULL, consumer text NOT NULL, producer text NOT NULL, event_id text NOT NULL,
 job_id uuid NOT NULL, step_id uuid NOT NULL, payload_hash bytea NOT NULL CHECK(octet_length(payload_hash)=32),
 processed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,consumer,producer,event_id),
 FOREIGN KEY(workspace_id,job_id,step_id) REFERENCES cos_v6.job_steps(workspace_id,job_id,id));

CREATE FUNCTION cos_v6.validate_owners() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM cos_v6.workspaces w LEFT JOIN cos_v6.workspace_memberships m ON (m.workspace_id,m.id)=(w.id,w.owner_membership_id)
 LEFT JOIN cos_v6.users u ON u.id=m.user_id WHERE w.state='ACTIVE' AND
 (m.id IS NULL OR m.state<>'ACTIVE' OR u.status<>'ACTIVE' OR u.verified_at IS NULL OR NOT EXISTS(SELECT 1 FROM cos_v6.user_identities i WHERE i.user_id=u.id)))
 THEN RAISE EXCEPTION 'invalid active owner'; END IF;
 IF EXISTS(SELECT 1 FROM cos_v6.workspace_memberships m WHERE cardinality(m.roles)<>(SELECT count(DISTINCT x) FROM unnest(m.roles) x))
 THEN RAISE EXCEPTION 'duplicate roles'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER validate_owner AFTER INSERT OR UPDATE OR DELETE ON cos_v6.workspaces DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cos_v6.validate_owners();
CREATE CONSTRAINT TRIGGER validate_member AFTER INSERT OR UPDATE OR DELETE ON cos_v6.workspace_memberships DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cos_v6.validate_owners();
CREATE CONSTRAINT TRIGGER validate_user AFTER INSERT OR UPDATE OR DELETE ON cos_v6.users DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cos_v6.validate_owners();
CREATE CONSTRAINT TRIGGER validate_identity AFTER INSERT OR UPDATE OR DELETE ON cos_v6.user_identities DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cos_v6.validate_owners();

CREATE FUNCTION cos_v6.actor() RETURNS uuid LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
BEGIN
 -- A transaction-wide snapshot can retain revoked grants despite workspace locks.
 IF current_setting('transaction_isolation') <> 'read committed' THEN
 RAISE EXCEPTION 'foundation requires READ COMMITTED isolation' USING ERRCODE='25001'; END IF;
 RETURN (SELECT p.user_id FROM cos_v6.database_principals p JOIN cos_v6.users u ON u.id=p.user_id
 WHERE p.database_role=session_user AND u.status='ACTIVE' AND u.verified_at IS NOT NULL
 AND EXISTS(SELECT 1 FROM cos_v6.user_identities i WHERE i.user_id=u.id));
END $$;
CREATE FUNCTION cos_v6.allowed(w uuid,b uuid,action text) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
 SELECT EXISTS(SELECT 1 FROM cos_v6.workspace_memberships m JOIN cos_v6.workspaces x ON x.id=m.workspace_id
 WHERE m.workspace_id=w AND m.user_id=cos_v6.actor() AND m.state='ACTIVE' AND x.state='ACTIVE'
 AND (b IS NULL OR EXISTS(SELECT 1 FROM cos_v6.brands z WHERE z.workspace_id=w AND z.id=b AND z.state='ACTIVE'))
 AND (action='manage' AND (m.id=x.owner_membership_id OR 'admin'=ANY(m.roles))
 OR action IN ('read','edit') AND (m.id=x.owner_membership_id OR b IS NULL OR EXISTS(SELECT 1 FROM cos_v6.brand_grants g WHERE g.workspace_id=w AND g.brand_id=b AND g.membership_id=m.id AND g.state='ACTIVE'))
 AND (action='read' OR m.id=x.owner_membership_id OR m.roles && ARRAY['admin','editor']::text[])))
$$;
CREATE FUNCTION cos_v6.authorize(w uuid,b uuid,action text) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE m uuid;
BEGIN
 -- Reject unsupported snapshots before acquiring the authorization lock.
 IF current_setting('transaction_isolation') <> 'read committed' THEN
 RAISE EXCEPTION 'foundation requires READ COMMITTED isolation' USING ERRCODE='25001'; END IF;
 -- All authorized writes serialize against permission changes in this workspace.
 PERFORM 1 FROM cos_v6.workspaces WHERE id=w FOR UPDATE;
 IF NOT cos_v6.allowed(w,b,action) THEN RAISE EXCEPTION 'forbidden' USING ERRCODE='42501'; END IF;
 SELECT id INTO m FROM cos_v6.workspace_memberships WHERE workspace_id=w AND user_id=cos_v6.actor();
 RETURN m;
END $$;
CREATE FUNCTION cos_v6.set_membership(w uuid,target uuid,new_roles text[],active boolean,reason text) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a uuid; old_roles text[];
BEGIN
 a:=cos_v6.authorize(w,NULL,'manage');
 IF reason IS NULL OR length(reason)=0 THEN RAISE EXCEPTION 'reason required'; END IF;
 SELECT roles INTO old_roles FROM cos_v6.workspace_memberships WHERE workspace_id=w AND id=target FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'unknown membership'; END IF;
 UPDATE cos_v6.workspace_memberships SET roles=new_roles,state=CASE WHEN active THEN 'ACTIVE' ELSE 'REVOKED' END WHERE workspace_id=w AND id=target;
 INSERT INTO cos_v6.audit_logs(workspace_id,actor_membership_id,action,metadata) VALUES(w,a,'membership.changed',jsonb_build_object('target',target,'old',old_roles,'new',new_roles,'reason',reason));
END $$;
CREATE FUNCTION cos_v6.set_brand_grant(w uuid,b uuid,target uuid,active boolean,connect boolean,reason text) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a uuid;
BEGIN
 a:=cos_v6.authorize(w,NULL,'manage');
 IF reason IS NULL OR length(reason)=0 THEN RAISE EXCEPTION 'reason required'; END IF;
 INSERT INTO cos_v6.brand_grants(workspace_id,brand_id,membership_id,granted_by_membership_id,state,can_connect)
 VALUES(w,b,target,a,CASE WHEN active THEN 'ACTIVE' ELSE 'REVOKED' END,connect)
 ON CONFLICT(workspace_id,brand_id,membership_id) DO UPDATE SET state=excluded.state,can_connect=excluded.can_connect,granted_by_membership_id=a;
 INSERT INTO cos_v6.audit_logs(workspace_id,actor_membership_id,action,metadata) VALUES(w,a,'grant.changed',jsonb_build_object('brand',b,'member',target,'active',active,'reason',reason));
END $$;
CREATE FUNCTION cos_v6.set_budget(w uuid,j uuid,c text,n bigint,reason text) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a uuid; result uuid; old_limit bigint;
BEGIN
 a:=cos_v6.authorize(w,NULL,'manage');
 IF n<0 OR n IS NULL OR reason IS NULL OR length(reason)=0 THEN RAISE EXCEPTION 'invalid budget'; END IF;
 SELECT id,limit_micros INTO result,old_limit FROM cos_v6.budget_accounts WHERE workspace_id=w AND job_id IS NOT DISTINCT FROM j AND currency=c FOR UPDATE;
 IF result IS NULL THEN
 INSERT INTO cos_v6.budget_accounts(workspace_id,scope,job_id,currency,limit_micros) VALUES(w,CASE WHEN j IS NULL THEN 'WORKSPACE' ELSE 'JOB' END,j,c,n) RETURNING id INTO result;
 ELSE UPDATE cos_v6.budget_accounts SET limit_micros=n WHERE id=result; END IF;
 INSERT INTO cos_v6.audit_logs(workspace_id,actor_membership_id,action,metadata) VALUES(w,a,'simulation.budget',jsonb_build_object('account',result,'old',old_limit,'new',n,'reason',reason));
 RETURN result;
END $$;
CREATE FUNCTION cos_v6.enqueue(w uuid,b uuid,op uuid,h bytea) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a uuid; j cos_v6.production_jobs;
BEGIN
 a:=cos_v6.authorize(w,b,'edit');
 SELECT * INTO j FROM cos_v6.production_jobs WHERE workspace_id=w AND logical_operation_id=op;
 IF FOUND THEN
 IF j.input_hash IS DISTINCT FROM h OR j.brand_id IS DISTINCT FROM b OR j.requested_by_membership_id IS DISTINCT FROM a THEN RAISE EXCEPTION 'idempotency conflict'; END IF;
 RETURN j.id; END IF;
 INSERT INTO cos_v6.production_jobs(workspace_id,brand_id,requested_by_membership_id,logical_operation_id,input_hash) VALUES(w,b,a,op,h) RETURNING * INTO j;
 INSERT INTO cos_v6.job_steps(workspace_id,brand_id,job_id) VALUES(w,b,j.id);
 RETURN j.id;
END $$;
CREATE FUNCTION cos_v6.claim(w uuid,b uuid,worker uuid,seconds int) RETURNS SETOF cos_v6.job_steps LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a uuid; s cos_v6.job_steps;
BEGIN
 a:=cos_v6.authorize(w,b,'edit');
 IF worker IS NULL OR seconds IS NULL OR seconds NOT BETWEEN 1 AND 300 THEN RAISE EXCEPTION 'invalid lease'; END IF;
 SELECT t.* INTO s FROM cos_v6.job_steps t JOIN cos_v6.production_jobs j ON (j.workspace_id,j.id)=(t.workspace_id,t.job_id)
 WHERE t.workspace_id=w AND t.brand_id=b AND t.status='QUEUED' AND t.next_attempt_at<=clock_timestamp()
 AND j.requested_by_membership_id=a ORDER BY t.next_attempt_at,t.id FOR UPDATE OF t SKIP LOCKED LIMIT 1;
 IF NOT FOUND THEN RETURN; END IF;
 UPDATE cos_v6.job_steps SET status='RUNNING',lease_owner=worker,lease_expires_at=clock_timestamp()+make_interval(secs=>seconds),heartbeat_at=clock_timestamp(),fencing_token=fencing_token+1 WHERE id=s.id RETURNING * INTO s;
 UPDATE cos_v6.production_jobs SET status='RUNNING' WHERE id=s.job_id;
 RETURN NEXT s;
END $$;
CREATE FUNCTION cos_v6.guard(w uuid,sid uuid,worker uuid,token bigint) RETURNS cos_v6.job_steps LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE s cos_v6.job_steps; a uuid;
BEGIN
 -- Workspace first, then step: consistent with grant mutation and all worker writes.
 PERFORM 1 FROM cos_v6.workspaces WHERE id=w FOR UPDATE;
 SELECT * INTO s FROM cos_v6.job_steps WHERE workspace_id=w AND id=sid FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'unknown step'; END IF;
 a:=cos_v6.authorize(w,s.brand_id,'edit');
 IF NOT EXISTS(SELECT 1 FROM cos_v6.production_jobs WHERE workspace_id=w AND id=s.job_id AND requested_by_membership_id=a)
 THEN RAISE EXCEPTION 'not original actor' USING ERRCODE='42501'; END IF;
 IF worker IS NULL OR token IS NULL OR s.lease_expires_at IS NULL OR s.status<>'RUNNING' OR s.lease_owner IS DISTINCT FROM worker OR s.fencing_token IS DISTINCT FROM token OR s.lease_expires_at<=clock_timestamp()
 THEN RAISE EXCEPTION 'stale fence'; END IF;
 RETURN s;
END $$;
CREATE FUNCTION cos_v6.heartbeat(w uuid,sid uuid,worker uuid,token bigint,seconds int) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
BEGIN
 PERFORM cos_v6.guard(w,sid,worker,token);
 IF seconds IS NULL OR seconds NOT BETWEEN 1 AND 300 THEN RAISE EXCEPTION 'invalid lease'; END IF;
 UPDATE cos_v6.job_steps SET heartbeat_at=clock_timestamp(),lease_expires_at=clock_timestamp()+make_interval(secs=>seconds) WHERE id=sid;
END $$;
CREATE FUNCTION cos_v6.reserve(w uuid,sid uuid,worker uuid,token bigint,c text,n bigint) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE s cos_v6.job_steps; r cos_v6.budget_reservations; account cos_v6.budget_accounts; count_accounts int:=0;
BEGIN
 s:=cos_v6.guard(w,sid,worker,token);
 IF n IS NULL OR n<0 THEN RAISE EXCEPTION 'invalid integer amount'; END IF;
 SELECT * INTO r FROM cos_v6.budget_reservations WHERE workspace_id=w AND step_id=sid;
 IF FOUND THEN IF r.reserved_micros<>n OR r.currency IS DISTINCT FROM c THEN RAISE EXCEPTION 'reservation replay mismatch'; END IF; RETURN r.id; END IF;
 FOR account IN SELECT * FROM cos_v6.budget_accounts WHERE workspace_id=w AND currency=c AND (scope='WORKSPACE' OR job_id=s.job_id) ORDER BY id FOR UPDATE LOOP
 count_accounts:=count_accounts+1;
 IF account.blocked OR account.reserved_micros::numeric+account.settled_micros::numeric+n>account.limit_micros THEN RAISE EXCEPTION 'BUDGET_EXCEEDED'; END IF;
 END LOOP;
 IF count_accounts<>2 THEN RAISE EXCEPTION 'BUDGET_MISSING'; END IF;
 INSERT INTO cos_v6.budget_reservations(workspace_id,job_id,step_id,currency,reserved_micros) VALUES(w,s.job_id,sid,c,n) RETURNING * INTO r;
 INSERT INTO cos_v6.reservation_allocations SELECT w,r.id,id,n FROM cos_v6.budget_accounts WHERE workspace_id=w AND currency=c AND (scope='WORKSPACE' OR job_id=s.job_id);
 UPDATE cos_v6.budget_accounts SET reserved_micros=reserved_micros+n WHERE id IN (SELECT budget_account_id FROM cos_v6.reservation_allocations WHERE workspace_id=w AND reservation_id=r.id);
 RETURN r.id;
END $$;
CREATE FUNCTION cos_v6.settle_internal(w uuid,sid uuid,n bigint,release boolean) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE r cos_v6.budget_reservations;
BEGIN
 SELECT * INTO r FROM cos_v6.budget_reservations WHERE workspace_id=w AND step_id=sid FOR UPDATE;
 IF NOT FOUND OR n IS NULL OR n<0 THEN RAISE EXCEPTION 'invalid settlement'; END IF;
 IF r.state<>'RESERVED' THEN
 IF (release AND r.state='RELEASED') OR (NOT release AND r.state='SETTLED' AND r.actual_micros=n) THEN RETURN; END IF;
 RAISE EXCEPTION 'terminal reservation conflict'; END IF;
 IF release AND EXISTS(SELECT 1 FROM cos_v6.provider_attempts WHERE workspace_id=w AND step_id=sid) THEN RAISE EXCEPTION 'uncertain intent retains reservation'; END IF;
 PERFORM 1 FROM cos_v6.budget_accounts WHERE id IN(SELECT budget_account_id FROM cos_v6.reservation_allocations WHERE workspace_id=w AND reservation_id=r.id) ORDER BY id FOR UPDATE;
 UPDATE cos_v6.budget_accounts SET reserved_micros=reserved_micros-r.reserved_micros,
 settled_micros=(settled_micros::numeric+CASE WHEN release THEN 0 ELSE n END)::bigint,
 blocked=blocked OR settled_micros::numeric+reserved_micros-r.reserved_micros+CASE WHEN release THEN 0 ELSE n END>limit_micros
 WHERE id IN(SELECT budget_account_id FROM cos_v6.reservation_allocations WHERE workspace_id=w AND reservation_id=r.id);
 UPDATE cos_v6.budget_reservations SET state=CASE WHEN release THEN 'RELEASED' ELSE 'SETTLED' END,actual_micros=CASE WHEN release THEN NULL ELSE n END WHERE id=r.id;
 IF NOT release THEN
 INSERT INTO cos_v6.usage_ledger(workspace_id,reservation_id,amount_units,currency) VALUES(w,r.id,n,r.currency);
 INSERT INTO cos_v6.usage_allocations SELECT w,l.id,a.budget_account_id,n FROM cos_v6.usage_ledger l JOIN cos_v6.reservation_allocations a ON (a.workspace_id,a.reservation_id)=(l.workspace_id,l.reservation_id) WHERE l.workspace_id=w AND l.reservation_id=r.id;
 END IF;
END $$;
CREATE FUNCTION cos_v6.release_reservation(w uuid,sid uuid,worker uuid,token bigint) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
BEGIN PERFORM cos_v6.guard(w,sid,worker,token); PERFORM cos_v6.settle_internal(w,sid,0,true); END $$;
CREATE FUNCTION cos_v6.record_intent(w uuid,sid uuid,worker uuid,token bigint) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE s cos_v6.job_steps; result uuid;
BEGIN
 s:=cos_v6.guard(w,sid,worker,token);
 IF NOT EXISTS(SELECT 1 FROM cos_v6.budget_reservations WHERE workspace_id=w AND step_id=sid AND state='RESERVED') THEN RAISE EXCEPTION 'reservation required'; END IF;
 INSERT INTO cos_v6.provider_attempts(workspace_id,job_id,step_id,claim_token) VALUES(w,s.job_id,sid,token)
 ON CONFLICT(workspace_id,step_id) DO NOTHING RETURNING id INTO result;
 IF result IS NULL THEN RAISE EXCEPTION 'intent exists: reconcile, never blind resubmit'; END IF;
 UPDATE cos_v6.job_steps SET submission_count=1 WHERE id=sid;
 RETURN result;
END $$;
CREATE FUNCTION cos_v6.complete(w uuid,sid uuid,worker uuid,token bigint,n bigint) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE s cos_v6.job_steps;
BEGIN
 s:=cos_v6.guard(w,sid,worker,token);
 PERFORM cos_v6.settle_internal(w,sid,n,false);
 UPDATE cos_v6.job_steps SET status='SUCCEEDED',lease_owner=NULL,lease_expires_at=NULL WHERE id=sid;
 UPDATE cos_v6.production_jobs SET status='SUCCEEDED' WHERE id=s.job_id;
 UPDATE cos_v6.provider_attempts SET state='SUCCEEDED' WHERE workspace_id=w AND step_id=sid;
 INSERT INTO cos_v6.event_outbox(workspace_id,job_id,step_id,type,data) VALUES(w,s.job_id,sid,'job.succeeded',jsonb_build_object('execution_mode','SIMULATED','amount_micros',n));
END $$;
CREATE FUNCTION cos_v6.consume(w uuid,sid uuid,worker uuid,token bigint,event text,h bytea,n bigint) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE prior cos_v6.event_inbox; s cos_v6.job_steps;
BEGIN
 PERFORM 1 FROM cos_v6.workspaces WHERE id=w FOR UPDATE;
 SELECT * INTO s FROM cos_v6.job_steps WHERE workspace_id=w AND id=sid;
 PERFORM cos_v6.authorize(w,s.brand_id,'edit');
 IF NOT EXISTS(SELECT 1 FROM cos_v6.production_jobs WHERE workspace_id=w AND id=s.job_id AND requested_by_membership_id=(SELECT id FROM cos_v6.workspace_memberships WHERE workspace_id=w AND user_id=cos_v6.actor())) THEN RAISE EXCEPTION 'not original actor'; END IF;
 SELECT * INTO prior FROM cos_v6.event_inbox WHERE workspace_id=w AND consumer='foundation' AND producer='local_fixture' AND event_id=event;
 IF FOUND THEN IF prior.payload_hash IS DISTINCT FROM h OR prior.step_id IS DISTINCT FROM sid THEN RAISE EXCEPTION 'inbox replay mismatch'; END IF; RETURN false; END IF;
 PERFORM cos_v6.complete(w,sid,worker,token,n);
 INSERT INTO cos_v6.event_inbox(workspace_id,consumer,producer,event_id,job_id,step_id,payload_hash) VALUES(w,'foundation','local_fixture',event,s.job_id,sid,h);
 RETURN true;
END $$;
CREATE FUNCTION cos_v6.recover(w uuid,b uuid) RETURNS int LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a uuid; s cos_v6.job_steps; result int:=0; uncertain boolean;
BEGIN
 a:=cos_v6.authorize(w,b,'edit');
 FOR s IN SELECT t.* FROM cos_v6.job_steps t JOIN cos_v6.production_jobs j ON (j.workspace_id,j.id)=(t.workspace_id,t.job_id)
 WHERE t.workspace_id=w AND t.brand_id=b AND j.requested_by_membership_id=a AND t.status='RUNNING' AND t.lease_expires_at<=clock_timestamp() FOR UPDATE OF t SKIP LOCKED LOOP
 uncertain:=EXISTS(SELECT 1 FROM cos_v6.provider_attempts WHERE workspace_id=w AND step_id=s.id);
 UPDATE cos_v6.job_steps SET status=CASE WHEN uncertain THEN 'RECONCILING' ELSE 'QUEUED' END,fencing_token=fencing_token+1,lease_owner=NULL,lease_expires_at=NULL WHERE id=s.id;
 UPDATE cos_v6.production_jobs SET status=CASE WHEN uncertain THEN 'RECONCILING' ELSE 'QUEUED' END WHERE id=s.job_id;
 IF uncertain THEN INSERT INTO cos_v6.event_outbox(workspace_id,job_id,step_id,type) VALUES(w,s.job_id,s.id,'job.reconciling'); END IF;
 result:=result+1;
 END LOOP;
 RETURN result;
END $$;
CREATE FUNCTION cos_v6.claim_event(w uuid,worker uuid,seconds int) RETURNS SETOF cos_v6.event_outbox LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a uuid; e cos_v6.event_outbox;
BEGIN
 a:=cos_v6.authorize(w,NULL,'read');
 IF worker IS NULL OR seconds IS NULL OR seconds NOT BETWEEN 1 AND 300 THEN RAISE EXCEPTION 'invalid lease'; END IF;
 SELECT o.* INTO e FROM cos_v6.event_outbox o JOIN cos_v6.production_jobs j ON (j.workspace_id,j.id)=(o.workspace_id,o.job_id)
 WHERE o.workspace_id=w AND j.requested_by_membership_id=a AND cos_v6.allowed(w,j.brand_id,'read')
 AND (o.state='PENDING' OR o.state='DELIVERING' AND o.lease_expires_at<=clock_timestamp()) ORDER BY o.occurred_at FOR UPDATE OF o SKIP LOCKED LIMIT 1;
 IF NOT FOUND THEN RETURN; END IF;
 UPDATE cos_v6.event_outbox SET state='DELIVERING',lease_owner=worker,lease_expires_at=clock_timestamp()+make_interval(secs=>seconds),fencing_token=fencing_token+1,delivery_count=delivery_count+1 WHERE event_id=e.event_id RETURNING * INTO e;
 RETURN NEXT e;
END $$;
CREATE FUNCTION cos_v6.ack_event(w uuid,event uuid,worker uuid,token bigint) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a uuid; n int;
BEGIN
 a:=cos_v6.authorize(w,NULL,'read');
 IF worker IS NULL OR token IS NULL THEN RAISE EXCEPTION 'stale event fence'; END IF;
 UPDATE cos_v6.event_outbox o SET state='DELIVERED',lease_owner=NULL,lease_expires_at=NULL
 FROM cos_v6.production_jobs j WHERE o.workspace_id=w AND o.event_id=event AND j.workspace_id=w AND j.id=o.job_id
 AND j.requested_by_membership_id=a AND cos_v6.allowed(w,j.brand_id,'read') AND o.state='DELIVERING' AND o.lease_owner=worker AND o.fencing_token=token AND o.lease_expires_at>clock_timestamp();
 GET DIAGNOSTICS n=ROW_COUNT; IF n<>1 THEN RAISE EXCEPTION 'stale event fence'; END IF;
END $$;

CREATE FUNCTION cos_v6.append_transition() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
BEGIN
 IF TG_OP='INSERT' OR OLD.status IS DISTINCT FROM NEW.status THEN
 INSERT INTO cos_v6.job_transitions(workspace_id,job_id,step_id,from_state,to_state,fencing_token)
 VALUES(NEW.workspace_id,NEW.job_id,NEW.id,CASE WHEN TG_OP='INSERT' THEN NULL ELSE OLD.status END,NEW.status,NEW.fencing_token);
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER step_transition AFTER INSERT OR UPDATE ON cos_v6.job_steps FOR EACH ROW EXECUTE FUNCTION cos_v6.append_transition();
CREATE FUNCTION cos_v6.immutable_history() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,cos_v6 AS $$
BEGIN RAISE EXCEPTION 'immutable history'; END $$;
CREATE TRIGGER immutable_usage BEFORE UPDATE OR DELETE ON cos_v6.usage_ledger FOR EACH ROW EXECUTE FUNCTION cos_v6.immutable_history();
CREATE TRIGGER immutable_usage_allocation BEFORE UPDATE OR DELETE ON cos_v6.usage_allocations FOR EACH ROW EXECUTE FUNCTION cos_v6.immutable_history();
CREATE TRIGGER immutable_reservation_allocation BEFORE UPDATE OR DELETE ON cos_v6.reservation_allocations FOR EACH ROW EXECUTE FUNCTION cos_v6.immutable_history();
CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON cos_v6.audit_logs FOR EACH ROW EXECUTE FUNCTION cos_v6.immutable_history();
CREATE TRIGGER immutable_transition BEFORE UPDATE OR DELETE ON cos_v6.job_transitions FOR EACH ROW EXECUTE FUNCTION cos_v6.immutable_history();
CREATE TRIGGER immutable_inbox BEFORE UPDATE OR DELETE ON cos_v6.event_inbox FOR EACH ROW EXECUTE FUNCTION cos_v6.immutable_history();
CREATE FUNCTION cos_v6.outbox_payload_immutable() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog,cos_v6 AS $$
BEGIN
 IF (NEW.event_id,NEW.workspace_id,NEW.job_id,NEW.step_id,NEW.type,NEW.data,NEW.occurred_at) IS DISTINCT FROM (OLD.event_id,OLD.workspace_id,OLD.job_id,OLD.step_id,OLD.type,OLD.data,OLD.occurred_at) THEN RAISE EXCEPTION 'immutable event payload'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_outbox_payload BEFORE UPDATE ON cos_v6.event_outbox FOR EACH ROW EXECUTE FUNCTION cos_v6.outbox_payload_immutable();
CREATE TRIGGER immutable_outbox_delete BEFORE DELETE ON cos_v6.event_outbox FOR EACH ROW EXECUTE FUNCTION cos_v6.immutable_history();

-- Runtime can SELECT only through real PostgreSQL RLS; no direct runtime DML anywhere.
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['workspaces','workspace_memberships','audit_logs','budget_accounts','budget_reservations','reservation_allocations','usage_ledger','usage_allocations','job_transitions','provider_attempts','event_outbox','event_inbox'] LOOP
 EXECUTE format('ALTER TABLE cos_v6.%I ENABLE ROW LEVEL SECURITY',t);
 IF t='workspaces' THEN
 EXECUTE format('CREATE POLICY tenant_read ON cos_v6.%I FOR SELECT TO cos_foundation_runtime USING(cos_v6.allowed(id,NULL,''read''))',t);
 ELSIF t IN ('budget_reservations','job_transitions','provider_attempts','event_outbox','event_inbox') THEN
 EXECUTE format('CREATE POLICY tenant_read ON cos_v6.%I FOR SELECT TO cos_foundation_runtime USING(EXISTS(SELECT 1 FROM cos_v6.production_jobs j WHERE j.workspace_id=%I.workspace_id AND j.id=%I.job_id))',t,t,t);
 ELSE
 EXECUTE format('CREATE POLICY tenant_read ON cos_v6.%I FOR SELECT TO cos_foundation_runtime USING(cos_v6.allowed(workspace_id,NULL,''manage''))',t);
 END IF;
 EXECUTE format('GRANT SELECT ON cos_v6.%I TO cos_foundation_runtime',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['brands','brand_grants','production_jobs','job_steps'] LOOP
 EXECUTE format('ALTER TABLE cos_v6.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY brand_read ON cos_v6.%I FOR SELECT TO cos_foundation_runtime USING(cos_v6.allowed(workspace_id,%s,''read''))',t,CASE WHEN t='brands' THEN 'id' ELSE 'brand_id' END);
 EXECUTE format('GRANT SELECT ON cos_v6.%I TO cos_foundation_runtime',t);
 END LOOP;
END $$;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA cos_v6 FROM PUBLIC;
REVOKE INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER ON ALL TABLES IN SCHEMA cos_v6 FROM cos_foundation_runtime;
GRANT EXECUTE ON FUNCTION cos_v6.actor(),cos_v6.allowed(uuid,uuid,text),cos_v6.set_membership(uuid,uuid,text[],boolean,text),cos_v6.set_brand_grant(uuid,uuid,uuid,boolean,boolean,text),cos_v6.set_budget(uuid,uuid,text,bigint,text),cos_v6.enqueue(uuid,uuid,uuid,bytea),cos_v6.claim(uuid,uuid,uuid,int),cos_v6.heartbeat(uuid,uuid,uuid,bigint,int),cos_v6.reserve(uuid,uuid,uuid,bigint,text,bigint),cos_v6.release_reservation(uuid,uuid,uuid,bigint),cos_v6.record_intent(uuid,uuid,uuid,bigint),cos_v6.complete(uuid,uuid,uuid,bigint,bigint),cos_v6.consume(uuid,uuid,uuid,bigint,text,bytea,bigint),cos_v6.recover(uuid,uuid),cos_v6.claim_event(uuid,uuid,int),cos_v6.ack_event(uuid,uuid,uuid,bigint) TO cos_foundation_runtime;
-- Future migrations must explicitly revoke PUBLIC EXECUTE on each new routine.
-- Schema-local defaults cannot remove the global PUBLIC function default.
-- The Alembic migration privilege audit rejects unsafe grants; no admin defaults change.
