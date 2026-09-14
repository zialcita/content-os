-- Additive identity branch. Foundation actor()/privileges are intentionally unchanged.
CREATE ROLE cos_identity_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE cos_identity_auth NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE cos_api_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT USAGE ON SCHEMA cos_v6 TO cos_identity_owner,cos_identity_auth,cos_api_runtime;

CREATE TABLE cos_v6.identity_profiles (
 identity_id uuid PRIMARY KEY REFERENCES cos_v6.user_identities,
 verified_email text NOT NULL, email_verified boolean NOT NULL CHECK(email_verified),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE cos_v6.login_transactions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), state_hash bytea UNIQUE NOT NULL CHECK(octet_length(state_hash)=32),
 browser_hash bytea NOT NULL CHECK(octet_length(browser_hash)=32), nonce text NOT NULL,
 verifier_ciphertext text NOT NULL, issuer text NOT NULL, return_path text NOT NULL,
 rate_key bytea NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL DEFAULT clock_timestamp()+interval '10 minutes',
 consumed_at timestamptz, finalized_at timestamptz);
CREATE INDEX identity_login_rate ON cos_v6.login_transactions(rate_key,created_at);
CREATE TABLE cos_v6.sessions (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES cos_v6.users,
 identity_id uuid NOT NULL REFERENCES cos_v6.user_identities,
 token_hash bytea UNIQUE NOT NULL CHECK(octet_length(token_hash)=32),
 csrf_secret_hash bytea NOT NULL CHECK(octet_length(csrf_secret_hash)=32),
 active_workspace_id uuid REFERENCES cos_v6.workspaces,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), expires_at timestamptz NOT NULL,
 revoked_at timestamptz, CHECK(expires_at>created_at));
-- Session user and issuer/subject identity must be the same person at the DB boundary.
ALTER TABLE cos_v6.user_identities ADD CONSTRAINT identity_user_pair UNIQUE(user_id,id);
ALTER TABLE cos_v6.sessions ADD CONSTRAINT session_identity_user_fk
 FOREIGN KEY(user_id,identity_id) REFERENCES cos_v6.user_identities(user_id,id);
CREATE TABLE cos_v6.onboarding_authorizations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code_hash bytea UNIQUE NOT NULL CHECK(octet_length(code_hash)=32),
 intended_issuer text NOT NULL, intended_subject text NOT NULL, intended_email text NOT NULL,
 expires_at timestamptz NOT NULL, initiated_at timestamptz, consumed_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE TABLE cos_v6.invitations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), workspace_id uuid NOT NULL REFERENCES cos_v6.workspaces,
 intended_issuer text NOT NULL, intended_email text NOT NULL,
 token_hash bytea UNIQUE NOT NULL CHECK(octet_length(token_hash)=32),
 roles text[] NOT NULL CHECK(cardinality(roles)>0 AND roles <@ ARRAY['admin','editor','reviewer','publisher','viewer']::text[] AND array_position(roles,NULL) IS NULL),
 created_by_membership_id uuid NOT NULL,
 expires_at timestamptz NOT NULL DEFAULT clock_timestamp()+interval '7 days',
 state text NOT NULL DEFAULT 'PENDING' CHECK(state IN ('PENDING','ACCEPTED','REVOKED')),
 accepted_identity_id uuid REFERENCES cos_v6.user_identities,
 revision bigint NOT NULL DEFAULT 1 CHECK(revision>0), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id), FOREIGN KEY(workspace_id,created_by_membership_id) REFERENCES cos_v6.workspace_memberships(workspace_id,id));
CREATE TABLE cos_v6.invitation_brands (
 workspace_id uuid NOT NULL, invitation_id uuid NOT NULL, brand_id uuid NOT NULL,
 PRIMARY KEY(workspace_id,invitation_id,brand_id),
 FOREIGN KEY(workspace_id,invitation_id) REFERENCES cos_v6.invitations(workspace_id,id),
 FOREIGN KEY(workspace_id,brand_id) REFERENCES cos_v6.brands(workspace_id,id));
CREATE TABLE cos_v6.identity_replays (
 user_id uuid NOT NULL REFERENCES cos_v6.users, workspace_id uuid NOT NULL REFERENCES cos_v6.workspaces,
 operation text NOT NULL, key text NOT NULL, request_hash bytea NOT NULL CHECK(octet_length(request_hash)=32),
 response jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(user_id,workspace_id,operation,key));
-- Additional columns, never replacement of the 0001 schema or actor bridge.
ALTER TABLE cos_v6.workspaces ADD COLUMN identity_revision bigint NOT NULL DEFAULT 1 CHECK(identity_revision>0);
ALTER TABLE cos_v6.workspace_memberships ADD COLUMN identity_revision bigint NOT NULL DEFAULT 1 CHECK(identity_revision>0);
ALTER TABLE cos_v6.brands ADD COLUMN identity_revision bigint NOT NULL DEFAULT 1 CHECK(identity_revision>0), ADD COLUMN timezone text NOT NULL DEFAULT 'UTC';

-- Definer owner is NOLOGIN/non-BYPASSRLS, with explicit policies instead of superuser bypass.
GRANT SELECT,INSERT,UPDATE ON cos_v6.users,cos_v6.user_identities,cos_v6.workspaces,cos_v6.workspace_memberships,cos_v6.brands,cos_v6.brand_grants TO cos_identity_owner;
GRANT INSERT ON cos_v6.audit_logs TO cos_identity_owner;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['workspaces','workspace_memberships','brands','brand_grants','audit_logs'] LOOP
 EXECUTE format('CREATE POLICY identity_definer ON cos_v6.%I TO cos_identity_owner USING(true) WITH CHECK(true)',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['identity_profiles','login_transactions','sessions','onboarding_authorizations','invitations','invitation_brands','identity_replays'] LOOP
 EXECUTE format('ALTER TABLE cos_v6.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE cos_v6.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY identity_definer ON cos_v6.%I TO cos_identity_owner USING(true) WITH CHECK(true)',t);
 EXECUTE format('GRANT SELECT,INSERT,UPDATE,DELETE ON cos_v6.%I TO cos_identity_owner',t);
 END LOOP;
END $$;

CREATE FUNCTION cos_v6.auth_start(sh bytea,bh bytea,n text,v text,i text,r text,rk bytea) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE t cos_v6.login_transactions;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended(encode(rk,'hex'),1));
 IF (SELECT count(*) FROM cos_v6.login_transactions WHERE rate_key=rk AND created_at>clock_timestamp()-interval '1 minute')>=10 THEN
 RAISE EXCEPTION 'RATE_LIMITED' USING ERRCODE='P0001'; END IF;
 INSERT INTO cos_v6.login_transactions(state_hash,browser_hash,nonce,verifier_ciphertext,issuer,return_path,rate_key)
 VALUES(sh,bh,n,v,i,r,rk) RETURNING * INTO t;
 RETURN jsonb_build_object('id',t.id,'expires_at',t.expires_at);
END $$;
CREATE FUNCTION cos_v6.auth_consume(sh bytea,bh bytea) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE t cos_v6.login_transactions;
BEGIN
 UPDATE cos_v6.login_transactions SET consumed_at=clock_timestamp()
 WHERE state_hash=sh AND browser_hash=bh AND consumed_at IS NULL AND expires_at>clock_timestamp() RETURNING * INTO t;
 IF NOT FOUND THEN RAISE EXCEPTION 'INVALID_LOGIN' USING ERRCODE='P0001'; END IF;
 RETURN jsonb_build_object('id',t.id,'nonce',t.nonce,'verifier_ciphertext',t.verifier_ciphertext,'issuer',t.issuer,'return_path',t.return_path);
END $$;
CREATE FUNCTION cos_v6.auth_finalize(tid uuid,i text,s text,e text,n text,th bytea,ch bytea) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE u uuid; ident uuid; t cos_v6.login_transactions; result uuid;
BEGIN
 SELECT * INTO t FROM cos_v6.login_transactions WHERE id=tid FOR UPDATE;
 IF NOT FOUND OR t.issuer IS DISTINCT FROM i OR t.consumed_at IS NULL OR t.finalized_at IS NOT NULL OR t.expires_at<=clock_timestamp() OR length(s)=0 OR length(e)=0 OR length(n)=0
 THEN RAISE EXCEPTION 'INVALID_LOGIN' USING ERRCODE='P0001'; END IF;
 -- Serialize first-login races on (issuer,subject), NEVER on email.
 PERFORM pg_advisory_xact_lock(hashtextextended(i || chr(1) || s,2));
 SELECT id,user_id INTO ident,u FROM cos_v6.user_identities WHERE issuer=i AND subject=s;
 IF u IS NULL THEN
 INSERT INTO cos_v6.users(display_name,status,verified_at) VALUES(n,'ACTIVE',clock_timestamp()) RETURNING id INTO u;
 INSERT INTO cos_v6.user_identities(user_id,issuer,subject,authenticated_at) VALUES(u,i,s,clock_timestamp()) RETURNING id INTO ident;
 ELSE
 IF NOT EXISTS(SELECT 1 FROM cos_v6.users WHERE id=u AND status='ACTIVE' AND verified_at IS NOT NULL) THEN RAISE EXCEPTION 'INVALID_LOGIN'; END IF;
 UPDATE cos_v6.user_identities SET authenticated_at=clock_timestamp() WHERE id=ident;
 END IF;
 INSERT INTO cos_v6.identity_profiles(identity_id,verified_email,email_verified) VALUES(ident,e,true)
 ON CONFLICT(identity_id) DO UPDATE SET verified_email=e,updated_at=clock_timestamp();
 INSERT INTO cos_v6.sessions(user_id,identity_id,token_hash,csrf_secret_hash,expires_at)
 VALUES(u,ident,th,ch,clock_timestamp()+interval '8 hours') RETURNING id INTO result;
 UPDATE cos_v6.login_transactions SET finalized_at=clock_timestamp(),verifier_ciphertext='' WHERE id=tid;
 RETURN result;
END $$;

CREATE FUNCTION cos_v6.api_actor() RETURNS uuid
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE u uuid;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN RAISE EXCEPTION 'READ_COMMITTED_REQUIRED' USING ERRCODE='25001'; END IF;
 SELECT s.user_id INTO u FROM cos_v6.sessions s JOIN cos_v6.users x ON x.id=s.user_id
 WHERE s.token_hash=sha256(convert_to(current_setting('cos.api_token',true),'UTF8'))
 AND s.revoked_at IS NULL AND s.expires_at>clock_timestamp() AND x.status='ACTIVE' AND x.verified_at IS NOT NULL
 AND EXISTS(SELECT 1 FROM cos_v6.user_identities i WHERE i.id=s.identity_id AND i.user_id=x.id)
 FOR SHARE OF s;
 RETURN u;
END $$;
CREATE FUNCTION cos_v6.api_require_write() RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE u uuid;
BEGIN
 u:=cos_v6.api_actor();
 IF u IS NULL THEN RAISE EXCEPTION 'UNAUTHENTICATED' USING ERRCODE='P0001'; END IF;
 IF NOT EXISTS(SELECT 1 FROM cos_v6.sessions WHERE token_hash=sha256(convert_to(current_setting('cos.api_token',true),'UTF8'))
 AND csrf_secret_hash=sha256(convert_to(current_setting('cos.api_csrf',true),'UTF8')))
 THEN RAISE EXCEPTION 'CSRF_INVALID' USING ERRCODE='P0001'; END IF;
 RETURN u;
END $$;
CREATE FUNCTION cos_v6.api_bind(token text,csrf text,writing boolean) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE u uuid;
BEGIN
 PERFORM set_config('cos.api_token',coalesce(token,''),true);
 PERFORM set_config('cos.api_csrf',coalesce(csrf,''),true);
 -- Serialize mutations before acquiring SHARE locks, avoiding concurrent lock upgrades.
 IF writing THEN
 PERFORM 1 FROM cos_v6.sessions WHERE token_hash=sha256(convert_to(token,'UTF8')) FOR UPDATE;
 END IF;
 u:=cos_v6.api_actor();
 IF u IS NULL THEN RAISE EXCEPTION 'UNAUTHENTICATED' USING ERRCODE='P0001'; END IF;
 IF writing THEN PERFORM cos_v6.api_require_write(); END IF;
 RETURN u;
END $$;
CREATE FUNCTION cos_v6.api_allowed(w uuid,b uuid,a text) RETURNS boolean
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE u uuid;
BEGIN
 u:=cos_v6.api_actor();
 RETURN EXISTS(SELECT 1 FROM cos_v6.workspace_memberships m JOIN cos_v6.workspaces x ON x.id=m.workspace_id
 WHERE m.workspace_id=w AND m.user_id=u AND m.state='ACTIVE' AND x.state='ACTIVE'
 AND (b IS NULL OR EXISTS(SELECT 1 FROM cos_v6.brands z WHERE z.id=b AND z.workspace_id=w AND z.state='ACTIVE'))
 AND CASE
 WHEN a='owner' THEN m.id=x.owner_membership_id
 WHEN a IN ('manage','manage_read') THEN b IS NULL AND (m.id=x.owner_membership_id OR 'admin'=ANY(m.roles))
 WHEN a IN ('read','edit','review','publish','connect') THEN
 (m.id=x.owner_membership_id OR b IS NULL AND a='read' OR EXISTS(SELECT 1 FROM cos_v6.brand_grants g WHERE g.workspace_id=w AND g.brand_id=b AND g.membership_id=m.id AND g.state='ACTIVE'
 AND (a<>'connect' OR 'admin'=ANY(m.roles) OR g.can_connect)))
 AND (a='read' OR m.id=x.owner_membership_id OR
 a='edit' AND m.roles && ARRAY['admin','editor']::text[] OR
 a='review' AND m.roles && ARRAY['admin','reviewer']::text[] OR
 a IN ('publish','connect') AND m.roles && ARRAY['admin','publisher']::text[])
 ELSE false END);
END $$;
CREATE FUNCTION cos_v6.api_authorize(w uuid,b uuid,a text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE u uuid; m uuid;
BEGIN
 u:=cos_v6.api_actor();
 IF u IS NULL THEN RAISE EXCEPTION 'UNAUTHENTICATED'; END IF;
 IF a NOT IN ('read','manage_read') THEN PERFORM cos_v6.api_require_write(); END IF;
 -- Same lock as foundation management: fresh READ COMMITTED snapshot after waiting.
 PERFORM 1 FROM cos_v6.workspaces WHERE id=w FOR UPDATE;
 IF NOT cos_v6.api_allowed(w,b,'read') THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 IF NOT cos_v6.api_allowed(w,b,a) THEN RAISE EXCEPTION 'FORBIDDEN'; END IF;
 SELECT id INTO m FROM cos_v6.workspace_memberships WHERE workspace_id=w AND user_id=u;
 RETURN m;
END $$;
CREATE FUNCTION cos_v6.api_session() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE u uuid; result jsonb;
BEGIN
 u:=cos_v6.api_actor();
 IF u IS NULL THEN RAISE EXCEPTION 'UNAUTHENTICATED'; END IF;
 SELECT jsonb_build_object('user',jsonb_build_object('user_id',x.id,'display_name',x.display_name,'state',x.status,'oidc_subject',i.subject,'verified_email',p.verified_email),
 'expires_at',s.expires_at,'active_workspace_id',CASE WHEN cos_v6.api_allowed(s.active_workspace_id,NULL,'read') THEN s.active_workspace_id ELSE NULL END)
 INTO result FROM cos_v6.sessions s JOIN cos_v6.users x ON x.id=s.user_id JOIN cos_v6.user_identities i ON i.id=s.identity_id
 JOIN cos_v6.identity_profiles p ON p.identity_id=i.id
 WHERE s.token_hash=sha256(convert_to(current_setting('cos.api_token',true),'UTF8'));
 RETURN result;
END $$;
CREATE FUNCTION cos_v6.api_logout() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
BEGIN
 PERFORM cos_v6.api_require_write();
 UPDATE cos_v6.sessions SET revoked_at=clock_timestamp() WHERE token_hash=sha256(convert_to(current_setting('cos.api_token',true),'UTF8'));
END $$;
CREATE FUNCTION cos_v6.api_switch(w uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
BEGIN
 PERFORM cos_v6.api_require_write(); PERFORM cos_v6.api_authorize(w,NULL,'read');
 UPDATE cos_v6.sessions SET active_workspace_id=w WHERE token_hash=sha256(convert_to(current_setting('cos.api_token',true),'UTF8'));
END $$;

CREATE FUNCTION cos_v6.api_onboarding(code text,email text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a cos_v6.onboarding_authorizations;
BEGIN
 UPDATE cos_v6.onboarding_authorizations SET initiated_at=clock_timestamp()
 WHERE code_hash=sha256(convert_to(code,'UTF8')) AND intended_email=email AND expires_at>clock_timestamp() AND consumed_at IS NULL AND initiated_at IS NULL RETURNING * INTO a;
 IF NOT FOUND THEN RAISE EXCEPTION 'ONBOARDING_DENIED'; END IF;
 RETURN jsonb_build_object('challenge_id',a.id,'expires_at',a.expires_at,'next_action','VERIFY_IDENTITY');
END $$;
CREATE FUNCTION cos_v6.api_workspace_json(w uuid) RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
 SELECT jsonb_build_object('workspace_id',x.id,'name',x.name,'timezone',x.timezone,'state',x.state,'revision',x.identity_revision,'owner_user_id',m.user_id)
 FROM cos_v6.workspaces x JOIN cos_v6.workspace_memberships m ON m.id=x.owner_membership_id WHERE x.id=w
$$;
CREATE FUNCTION cos_v6.api_create_workspace(challenge uuid,n text,tz text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a cos_v6.onboarding_authorizations; u uuid; w uuid; m uuid;
BEGIN
 u:=cos_v6.api_require_write();
 SELECT * INTO a FROM cos_v6.onboarding_authorizations WHERE id=challenge FOR UPDATE;
 IF NOT FOUND OR a.initiated_at IS NULL OR a.consumed_at IS NOT NULL OR a.expires_at<=clock_timestamp()
 OR NOT EXISTS(SELECT 1 FROM cos_v6.sessions ss JOIN cos_v6.user_identities i ON i.id=ss.identity_id
 WHERE ss.token_hash=sha256(convert_to(current_setting('cos.api_token',true),'UTF8')) AND i.issuer=a.intended_issuer AND i.subject=a.intended_subject)
 THEN RAISE EXCEPTION 'ONBOARDING_DENIED'; END IF;
 IF length(n) NOT BETWEEN 1 AND 200 OR NOT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=tz) THEN RAISE EXCEPTION 'INVALID_INPUT'; END IF;
 INSERT INTO cos_v6.workspaces(name,timezone) VALUES(n,tz) RETURNING id INTO w;
 INSERT INTO cos_v6.workspace_memberships(workspace_id,user_id,state,verified_at) VALUES(w,u,'ACTIVE',clock_timestamp()) RETURNING id INTO m;
 UPDATE cos_v6.workspaces SET owner_membership_id=m,state='ACTIVE' WHERE id=w;
 UPDATE cos_v6.onboarding_authorizations SET consumed_at=clock_timestamp() WHERE id=challenge;
 INSERT INTO cos_v6.audit_logs(workspace_id,actor_membership_id,action,metadata) VALUES(w,m,'workspace.onboarded',jsonb_build_object('authorization_id',challenge));
 RETURN cos_v6.api_workspace_json(w);
END $$;

CREATE FUNCTION cos_v6.api_brand_json(b uuid) RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
 SELECT jsonb_build_object('brand_id',id,'workspace_id',workspace_id,'name',name,'timezone',timezone,'revision',identity_revision,'current_profile_version_id',NULL) FROM cos_v6.brands WHERE id=b
$$;
CREATE FUNCTION cos_v6.api_member_json(m uuid) RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
 SELECT jsonb_build_object('membership_id',id,'workspace_id',workspace_id,'user_id',user_id,'roles',ARRAY(SELECT upper(r) FROM unnest(roles) r),'state',state,'revision',identity_revision) FROM cos_v6.workspace_memberships WHERE id=m
$$;
CREATE FUNCTION cos_v6.api_invitation_json(i uuid) RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
 SELECT jsonb_build_object('invitation_id',id,'workspace_id',workspace_id,'email',intended_email,'roles',ARRAY(SELECT upper(r) FROM unnest(roles) r),
 'brand_ids',ARRAY(SELECT brand_id FROM cos_v6.invitation_brands b WHERE b.invitation_id=i ORDER BY brand_id),'expires_at',expires_at,
 'state',CASE WHEN state='PENDING' AND expires_at<=clock_timestamp() THEN 'EXPIRED' ELSE state END,'revision',revision)
 FROM cos_v6.invitations WHERE id=i
$$;
CREATE FUNCTION cos_v6.api_read(kind text,w uuid,target uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE result jsonb;
BEGIN
 PERFORM cos_v6.api_authorize(w,CASE WHEN kind='brand' THEN target ELSE NULL END,CASE WHEN kind='member' THEN 'manage_read' ELSE 'read' END);
 IF kind='workspace' THEN result:=cos_v6.api_workspace_json(w);
 ELSIF kind='brand' THEN result:=cos_v6.api_brand_json(target);
 ELSIF kind='member' THEN
 IF EXISTS(SELECT 1 FROM cos_v6.workspace_memberships WHERE id=target AND workspace_id=w) THEN result:=cos_v6.api_member_json(target); END IF;
 ELSE RAISE EXCEPTION 'INVALID_INPUT'; END IF;
 IF result IS NULL THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 RETURN result;
END $$;
-- Lists return stable keys privately to the server; API wraps them in signed scope-bound cursors.
CREATE FUNCTION cos_v6.api_list(kind text,w uuid,target uuid,after_time timestamptz,after_id uuid,n integer) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE result jsonb;
BEGIN
 IF cos_v6.api_actor() IS NULL THEN RAISE EXCEPTION 'UNAUTHENTICATED'; END IF;
 IF n IS NULL OR n NOT BETWEEN 1 AND 101 THEN RAISE EXCEPTION 'INVALID_INPUT'; END IF;
 IF kind<>'workspace' THEN PERFORM cos_v6.api_authorize(w,NULL,CASE WHEN kind IN ('member','grant','invitation') THEN 'manage_read' ELSE 'read' END); END IF;
 IF kind='workspace' THEN
 SELECT coalesce(jsonb_agg(z),'[]') INTO result FROM (SELECT x.created_at AS sort_time,x.id AS sort_id,cos_v6.api_workspace_json(x.id) AS item FROM cos_v6.workspaces x WHERE cos_v6.api_allowed(x.id,NULL,'read') AND (after_id IS NULL OR (x.created_at,x.id)>(after_time,after_id)) ORDER BY x.created_at,x.id LIMIT n) z;
 ELSIF kind='brand' THEN
 SELECT coalesce(jsonb_agg(z),'[]') INTO result FROM (SELECT x.created_at AS sort_time,x.id AS sort_id,cos_v6.api_brand_json(x.id) AS item FROM cos_v6.brands x WHERE x.workspace_id=w AND cos_v6.api_allowed(w,x.id,'read') AND (after_id IS NULL OR (x.created_at,x.id)>(after_time,after_id)) ORDER BY x.created_at,x.id LIMIT n) z;
 ELSIF kind='member' THEN
 SELECT coalesce(jsonb_agg(z),'[]') INTO result FROM (SELECT x.created_at AS sort_time,x.id AS sort_id,cos_v6.api_member_json(x.id) AS item FROM cos_v6.workspace_memberships x WHERE x.workspace_id=w AND (after_id IS NULL OR (x.created_at,x.id)>(after_time,after_id)) ORDER BY x.created_at,x.id LIMIT n) z;
 ELSIF kind='invitation' THEN
 SELECT coalesce(jsonb_agg(z),'[]') INTO result FROM (SELECT x.created_at AS sort_time,x.id AS sort_id,cos_v6.api_invitation_json(x.id) AS item FROM cos_v6.invitations x WHERE x.workspace_id=w AND (after_id IS NULL OR (x.created_at,x.id)>(after_time,after_id)) ORDER BY x.created_at,x.id LIMIT n) z;
 ELSIF kind='grant' THEN
 IF NOT EXISTS(SELECT 1 FROM cos_v6.workspace_memberships WHERE workspace_id=w AND id=target) THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 SELECT coalesce(jsonb_agg(z),'[]') INTO result FROM (SELECT x.created_at AS sort_time,x.brand_id AS sort_id,jsonb_build_object('workspace_id',w,'membership_id',target,'brand_id',x.brand_id,'can_connect_social',x.can_connect) AS item FROM cos_v6.brand_grants x WHERE x.workspace_id=w AND x.membership_id=target AND x.state='ACTIVE' AND (after_id IS NULL OR (x.created_at,x.brand_id)>(after_time,after_id)) ORDER BY x.created_at,x.brand_id LIMIT n) z;
 ELSE RAISE EXCEPTION 'INVALID_INPUT'; END IF;
 RETURN result;
END $$;

CREATE FUNCTION cos_v6.api_write_brand(w uuid,b uuid,n text,tz text,expected bigint,key text,h bytea) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE m uuid; prior cos_v6.identity_replays; result jsonb; v_operation text;
BEGIN
 m:=cos_v6.api_authorize(w,CASE WHEN b IS NULL THEN NULL ELSE b END,CASE WHEN b IS NULL THEN 'manage' ELSE 'edit' END);
 v_operation:=CASE WHEN b IS NULL THEN 'createBrand' ELSE 'editBrand:'||b::text END;
 IF key IS NULL OR length(key) NOT BETWEEN 1 AND 200 THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_REQUIRED'; END IF;
 SELECT * INTO prior FROM cos_v6.identity_replays WHERE user_id=cos_v6.api_actor() AND workspace_id=w AND identity_replays.operation=v_operation AND identity_replays.key=api_write_brand.key;
 IF FOUND THEN IF prior.request_hash IS DISTINCT FROM h THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF; RETURN prior.response; END IF;
 IF length(n) NOT BETWEEN 1 AND 200 OR NOT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=tz) THEN RAISE EXCEPTION 'INVALID_INPUT'; END IF;
 IF b IS NULL THEN INSERT INTO cos_v6.brands(workspace_id,name,timezone) VALUES(w,n,tz) RETURNING id INTO b;
 ELSE
 IF expected IS NULL THEN RAISE EXCEPTION 'PRECONDITION_REQUIRED'; END IF;
 UPDATE cos_v6.brands SET name=n,timezone=tz,identity_revision=identity_revision+1 WHERE workspace_id=w AND id=b AND identity_revision=expected;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_VERSION'; END IF;
 END IF;
 result:=cos_v6.api_brand_json(b);
 INSERT INTO cos_v6.identity_replays(user_id,workspace_id,operation,key,request_hash,response) VALUES(cos_v6.api_actor(),w,v_operation,key,h,result);
 INSERT INTO cos_v6.audit_logs(workspace_id,actor_membership_id,action,metadata) VALUES(w,m,v_operation,jsonb_build_object('brand_id',b));
 RETURN result;
END $$;
CREATE FUNCTION cos_v6.api_edit_member(w uuid,target uuid,roles text[],active boolean,expected bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a uuid; old jsonb;
BEGIN
 a:=cos_v6.api_authorize(w,NULL,'manage');
 IF expected IS NULL THEN RAISE EXCEPTION 'PRECONDITION_REQUIRED'; END IF;
 IF NOT EXISTS(SELECT 1 FROM cos_v6.workspace_memberships WHERE workspace_id=w AND id=target) THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 IF EXISTS(SELECT 1 FROM cos_v6.workspaces WHERE id=w AND owner_membership_id=target) THEN RAISE EXCEPTION 'OWNER_PROTECTED'; END IF;
 old:=cos_v6.api_member_json(target);
 IF active AND cardinality(roles)=0 THEN RAISE EXCEPTION 'INVALID_INPUT'; END IF;
 UPDATE cos_v6.workspace_memberships SET roles=coalesce(api_edit_member.roles,workspace_memberships.roles),state=CASE WHEN active THEN 'ACTIVE' ELSE 'REVOKED' END,identity_revision=identity_revision+1
 WHERE workspace_id=w AND id=target AND identity_revision=expected;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_VERSION'; END IF;
 INSERT INTO cos_v6.audit_logs(workspace_id,actor_membership_id,action,metadata) VALUES(w,a,'membership.changed',jsonb_build_object('old',old,'new',cos_v6.api_member_json(target)));
 RETURN cos_v6.api_member_json(target);
END $$;
CREATE FUNCTION cos_v6.api_grant(w uuid,b uuid,target uuid,active boolean,connect boolean,expected bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a uuid; old jsonb;
BEGIN
 a:=cos_v6.api_authorize(w,NULL,'manage');
 IF expected IS NULL THEN RAISE EXCEPTION 'PRECONDITION_REQUIRED'; END IF;
 IF NOT EXISTS(SELECT 1 FROM cos_v6.workspace_memberships WHERE workspace_id=w AND id=target) OR NOT EXISTS(SELECT 1 FROM cos_v6.brands WHERE workspace_id=w AND id=b AND state='ACTIVE') THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 UPDATE cos_v6.workspace_memberships SET identity_revision=identity_revision+1 WHERE workspace_id=w AND id=target AND identity_revision=expected;
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_VERSION'; END IF;
 SELECT to_jsonb(g) INTO old FROM cos_v6.brand_grants g WHERE workspace_id=w AND brand_id=b AND membership_id=target;
 INSERT INTO cos_v6.brand_grants(workspace_id,brand_id,membership_id,granted_by_membership_id,state,can_connect) VALUES(w,b,target,a,CASE WHEN active THEN 'ACTIVE' ELSE 'REVOKED' END,connect)
 ON CONFLICT(workspace_id,brand_id,membership_id) DO UPDATE SET state=excluded.state,can_connect=excluded.can_connect,granted_by_membership_id=a;
 INSERT INTO cos_v6.audit_logs(workspace_id,actor_membership_id,action,metadata) VALUES(w,a,'grant.changed',jsonb_build_object('old',old,'brand_id',b,'membership_id',target,'active',active,'can_connect',connect));
 RETURN jsonb_build_object('workspace_id',w,'brand_id',b,'membership_id',target,'can_connect_social',connect);
END $$;
CREATE FUNCTION cos_v6.api_invite(w uuid,i text,e text,r text[],brands uuid[],th bytea) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a uuid; result uuid; b uuid;
BEGIN
 a:=cos_v6.api_authorize(w,NULL,'manage');
 IF length(e)=0 OR length(i)=0 OR cardinality(brands)=0 THEN RAISE EXCEPTION 'INVALID_INPUT'; END IF;
 IF (SELECT count(DISTINCT x) FROM unnest(r) x)<>cardinality(r) THEN RAISE EXCEPTION 'INVALID_INPUT'; END IF;
 INSERT INTO cos_v6.invitations(workspace_id,intended_issuer,intended_email,roles,token_hash,created_by_membership_id) VALUES(w,i,e,r,th,a) RETURNING id INTO result;
 FOREACH b IN ARRAY brands LOOP
 IF NOT EXISTS(SELECT 1 FROM cos_v6.brands WHERE workspace_id=w AND id=b AND state='ACTIVE') THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 INSERT INTO cos_v6.invitation_brands VALUES(w,result,b);
 END LOOP;
 INSERT INTO cos_v6.audit_logs(workspace_id,actor_membership_id,action,metadata) VALUES(w,a,'invitation.local_receipt',jsonb_build_object('invitation_id',result));
 RETURN cos_v6.api_invitation_json(result);
END $$;
CREATE FUNCTION cos_v6.api_accept_invite(token text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE u uuid; i cos_v6.invitations; ident uuid; m uuid; b uuid;
BEGIN
 u:=cos_v6.api_require_write();
 SELECT * INTO i FROM cos_v6.invitations WHERE token_hash=sha256(convert_to(token,'UTF8'));
 IF NOT FOUND THEN RAISE EXCEPTION 'INVITATION_INVALID'; END IF;
 PERFORM 1 FROM cos_v6.workspaces WHERE id=i.workspace_id FOR UPDATE;
 SELECT * INTO i FROM cos_v6.invitations WHERE id=i.id FOR UPDATE;
 IF i.state<>'PENDING' OR i.expires_at<=clock_timestamp() OR NOT EXISTS(SELECT 1 FROM cos_v6.workspaces WHERE id=i.workspace_id AND state='ACTIVE') THEN RAISE EXCEPTION 'INVITATION_INVALID'; END IF;
 -- Invitation creator must STILL have membership management authority.
 IF NOT EXISTS(SELECT 1 FROM cos_v6.workspace_memberships mm JOIN cos_v6.workspaces w ON w.id=mm.workspace_id WHERE mm.id=i.created_by_membership_id AND mm.state='ACTIVE' AND (mm.id=w.owner_membership_id OR 'admin'=ANY(mm.roles))) THEN RAISE EXCEPTION 'INVITATION_INVALID'; END IF;
 SELECT id INTO ident FROM cos_v6.user_identities x WHERE x.user_id=u AND x.issuer=i.intended_issuer AND EXISTS(SELECT 1 FROM cos_v6.identity_profiles p WHERE p.identity_id=x.id AND p.verified_email=i.intended_email AND p.email_verified)
 AND EXISTS(SELECT 1 FROM cos_v6.sessions ss WHERE ss.identity_id=x.id AND ss.token_hash=sha256(convert_to(current_setting('cos.api_token',true),'UTF8')));
 IF ident IS NULL THEN RAISE EXCEPTION 'INVITATION_IDENTITY_MISMATCH'; END IF;
 -- Never use invitations to overwrite an existing membership/owner.
 IF EXISTS(SELECT 1 FROM cos_v6.workspace_memberships WHERE workspace_id=i.workspace_id AND user_id=u) THEN RAISE EXCEPTION 'MEMBERSHIP_EXISTS'; END IF;
 INSERT INTO cos_v6.workspace_memberships(workspace_id,user_id,roles,state,verified_at) VALUES(i.workspace_id,u,i.roles,'ACTIVE',clock_timestamp()) RETURNING id INTO m;
 FOR b IN SELECT brand_id FROM cos_v6.invitation_brands WHERE invitation_id=i.id LOOP
 IF NOT EXISTS(SELECT 1 FROM cos_v6.brands WHERE id=b AND workspace_id=i.workspace_id AND state='ACTIVE') THEN RAISE EXCEPTION 'INVITATION_INVALID'; END IF;
 INSERT INTO cos_v6.brand_grants(workspace_id,brand_id,membership_id,granted_by_membership_id,state) VALUES(i.workspace_id,b,m,i.created_by_membership_id,'ACTIVE');
 END LOOP;
 UPDATE cos_v6.invitations SET state='ACCEPTED',accepted_identity_id=ident,revision=revision+1 WHERE id=i.id;
 INSERT INTO cos_v6.audit_logs(workspace_id,actor_membership_id,action,metadata) VALUES(i.workspace_id,m,'invitation.accepted',jsonb_build_object('invitation_id',i.id,'identity_id',ident));
 RETURN cos_v6.api_member_json(m);
END $$;
CREATE FUNCTION cos_v6.api_revoke_invite(w uuid,i uuid,expected bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE a uuid;
BEGIN
 a:=cos_v6.api_authorize(w,NULL,'manage');
 IF expected IS NULL THEN RAISE EXCEPTION 'PRECONDITION_REQUIRED'; END IF;
 IF NOT EXISTS(SELECT 1 FROM cos_v6.invitations WHERE workspace_id=w AND id=i) THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 UPDATE cos_v6.invitations SET state='REVOKED',revision=revision+1 WHERE workspace_id=w AND id=i AND revision=expected AND state='PENDING';
 IF NOT FOUND THEN RAISE EXCEPTION 'STALE_VERSION'; END IF;
 INSERT INTO cos_v6.audit_logs(workspace_id,actor_membership_id,action,metadata) VALUES(w,a,'invitation.revoked',jsonb_build_object('invitation_id',i));
 RETURN cos_v6.api_invitation_json(i);
END $$;

-- Runtime table reads are also RLS guarded. There are no runtime table writes.
GRANT SELECT ON cos_v6.workspaces,cos_v6.workspace_memberships,cos_v6.brands,cos_v6.brand_grants TO cos_api_runtime;
CREATE POLICY api_read ON cos_v6.workspaces FOR SELECT TO cos_api_runtime USING(cos_v6.api_allowed(id,NULL,'read'));
CREATE POLICY api_read ON cos_v6.workspace_memberships FOR SELECT TO cos_api_runtime USING(cos_v6.api_allowed(workspace_id,NULL,'manage'));
CREATE POLICY api_read ON cos_v6.brands FOR SELECT TO cos_api_runtime USING(cos_v6.api_allowed(workspace_id,id,'read'));
CREATE POLICY api_read ON cos_v6.brand_grants FOR SELECT TO cos_api_runtime USING(cos_v6.api_allowed(workspace_id,NULL,'manage'));

-- Ownership/ACL finalization is intentionally scoped to functions introduced here.
DO $$ DECLARE f record; BEGIN
 FOR f IN SELECT p.oid::regprocedure AS sig FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='cos_v6' AND p.proname = ANY(ARRAY[
 'auth_start','auth_consume','auth_finalize','api_actor','api_require_write','api_bind','api_allowed','api_authorize',
 'api_session','api_logout','api_switch','api_onboarding','api_workspace_json','api_create_workspace','api_brand_json',
 'api_member_json','api_invitation_json','api_read','api_list','api_write_brand','api_edit_member','api_grant',
 'api_invite','api_accept_invite','api_revoke_invite']) LOOP
 EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC',f.sig);
 EXECUTE format('ALTER FUNCTION %s OWNER TO cos_identity_owner',f.sig);
 END LOOP;
END $$;
GRANT EXECUTE ON FUNCTION cos_v6.auth_start(bytea,bytea,text,text,text,text,bytea),cos_v6.auth_consume(bytea,bytea),cos_v6.auth_finalize(uuid,text,text,text,text,bytea,bytea) TO cos_identity_auth;
GRANT EXECUTE ON FUNCTION cos_v6.api_bind(text,text,boolean),cos_v6.api_actor(),cos_v6.api_allowed(uuid,uuid,text),cos_v6.api_authorize(uuid,uuid,text),cos_v6.api_session(),cos_v6.api_logout(),cos_v6.api_switch(uuid),cos_v6.api_onboarding(text,text),cos_v6.api_create_workspace(uuid,text,text),cos_v6.api_read(text,uuid,uuid),cos_v6.api_list(text,uuid,uuid,timestamptz,uuid,integer),cos_v6.api_write_brand(uuid,uuid,text,text,bigint,text,bytea),cos_v6.api_edit_member(uuid,uuid,text[],boolean,bigint),cos_v6.api_grant(uuid,uuid,uuid,boolean,boolean,bigint),cos_v6.api_invite(uuid,text,text,text[],uuid[],bytea),cos_v6.api_accept_invite(text),cos_v6.api_revoke_invite(uuid,uuid,bigint) TO cos_api_runtime;
