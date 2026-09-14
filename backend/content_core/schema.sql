-- M1 non-paid local ingestion, deliberately separate from LOCAL_SIMULATION jobs.
CREATE ROLE cos_content_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE cos_content_worker NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT USAGE ON SCHEMA cos_v6 TO cos_content_owner,cos_content_worker;
GRANT EXECUTE ON FUNCTION cos_v6.api_actor(),cos_v6.api_authorize(uuid,uuid,text) TO cos_content_owner;
GRANT SELECT ON cos_v6.workspaces,cos_v6.workspace_memberships,cos_v6.brands,cos_v6.brand_grants,cos_v6.users,cos_v6.user_identities TO cos_content_owner;
-- SELECT FOR UPDATE needs UPDATE on at least one column. No service inherits this role.
GRANT UPDATE(id) ON cos_v6.workspaces TO cos_content_owner;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['workspaces','workspace_memberships','brands','brand_grants'] LOOP
 EXECUTE format('CREATE POLICY content_identity_read ON cos_v6.%I TO cos_content_owner USING(true)',t);
 END LOOP;
END $$;

CREATE TABLE cos_v6.content_capacity (
 workspace_id uuid PRIMARY KEY REFERENCES cos_v6.workspaces,
 limit_bytes bigint NOT NULL DEFAULT 100000000000 CHECK(limit_bytes BETWEEN 0 AND 1099511627776),
 reserved_bytes bigint NOT NULL DEFAULT 0 CHECK(reserved_bytes>=0));
CREATE TABLE cos_v6.brand_graph_locks (
 workspace_id uuid NOT NULL,brand_id uuid NOT NULL,epoch bigint NOT NULL DEFAULT 0,
 PRIMARY KEY(workspace_id,brand_id),FOREIGN KEY(workspace_id,brand_id) REFERENCES cos_v6.brands(workspace_id,id));
CREATE TABLE cos_v6.source_assets (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),workspace_id uuid NOT NULL,brand_id uuid NOT NULL,
 title text NOT NULL CHECK(length(title) BETWEEN 1 AND 200),source_type text NOT NULL DEFAULT 'UPLOAD' CHECK(source_type='UPLOAD'),
 current_version_id uuid,revision bigint NOT NULL DEFAULT 1 CHECK(revision>0),created_by_membership_id uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,brand_id,id),FOREIGN KEY(workspace_id,brand_id) REFERENCES cos_v6.brands(workspace_id,id),
 FOREIGN KEY(workspace_id,created_by_membership_id) REFERENCES cos_v6.workspace_memberships(workspace_id,id));
CREATE TABLE cos_v6.upload_intents (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),workspace_id uuid NOT NULL,brand_id uuid NOT NULL,source_asset_id uuid NOT NULL,
 requested_by_membership_id uuid NOT NULL,quarantine_key text NOT NULL UNIQUE,
 storage_mode text NOT NULL DEFAULT 'LOCAL_PRIVATE_DEVELOPMENT' CHECK(storage_mode='LOCAL_PRIVATE_DEVELOPMENT'),
 expected_size bigint NOT NULL CHECK(expected_size BETWEEN 1 AND 2000000000),
 expected_hash bytea NOT NULL CHECK(octet_length(expected_hash)=32),mime_type text NOT NULL CHECK(mime_type IN ('text/plain','application/pdf','audio/wav','video/mp4')),
 rights_assertion text NOT NULL CHECK(length(rights_assertion) BETWEEN 1 AND 2000),
 state text NOT NULL DEFAULT 'UPLOADING' CHECK(state IN ('UPLOADING','QUEUED','SCANNING','CLEARED','BLOCKED','REJECTED','CANCELLED','PURGED')),
 revision bigint NOT NULL DEFAULT 1 CHECK(revision>0),error_code text,completed_source_version_id uuid,
 expires_at timestamptz NOT NULL DEFAULT clock_timestamp()+interval '24 hours',created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,brand_id,id),UNIQUE(workspace_id,brand_id,source_asset_id),
 FOREIGN KEY(workspace_id,brand_id,source_asset_id) REFERENCES cos_v6.source_assets(workspace_id,brand_id,id),
 FOREIGN KEY(workspace_id,requested_by_membership_id) REFERENCES cos_v6.workspace_memberships(workspace_id,id),
 CHECK(quarantine_key=workspace_id::text||'/'||brand_id::text||'/'||id::text),
 CHECK(mime_type NOT IN ('text/plain','application/pdf') OR expected_size<=50000000));
CREATE TABLE cos_v6.upload_parts (
 workspace_id uuid NOT NULL,brand_id uuid NOT NULL,upload_id uuid NOT NULL,part_number integer NOT NULL CHECK(part_number BETWEEN 1 AND 256),
 size_bytes integer NOT NULL CHECK(size_bytes BETWEEN 1 AND 8388608),sha256 bytea NOT NULL CHECK(octet_length(sha256)=32),
 PRIMARY KEY(workspace_id,brand_id,upload_id,part_number),
 FOREIGN KEY(workspace_id,brand_id,upload_id) REFERENCES cos_v6.upload_intents(workspace_id,brand_id,id));
CREATE TABLE cos_v6.ingestion_jobs (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),workspace_id uuid NOT NULL,brand_id uuid NOT NULL,upload_id uuid NOT NULL,
 job_kind text NOT NULL CHECK(job_kind IN ('INGEST','PURGE_CANCELLED_UPLOAD')),
 paid_authority text NOT NULL DEFAULT 'NONE' CHECK(paid_authority='NONE'),
 status text NOT NULL DEFAULT 'QUEUED' CHECK(status IN ('QUEUED','RUNNING','SUCCEEDED','BLOCKED','REJECTED','CANCELLED')),
 fencing_token bigint NOT NULL DEFAULT 0 CHECK(fencing_token>=0),claim_hash bytea,lease_expires_at timestamptz,claimed_by name,
 attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),error_code text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,brand_id,id),UNIQUE(workspace_id,brand_id,upload_id,job_kind),
 FOREIGN KEY(workspace_id,brand_id,upload_id) REFERENCES cos_v6.upload_intents(workspace_id,brand_id,id),
 CHECK((status='RUNNING')=(claim_hash IS NOT NULL)),CHECK((claim_hash IS NULL)=(lease_expires_at IS NULL)),
 CHECK((claim_hash IS NULL)=(claimed_by IS NULL)),CHECK(claim_hash IS NULL OR octet_length(claim_hash)=32));
CREATE INDEX content_queue ON cos_v6.ingestion_jobs(workspace_id,brand_id,status,created_at,id);
CREATE TABLE cos_v6.ingestion_events (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),workspace_id uuid NOT NULL,brand_id uuid NOT NULL,job_id uuid NOT NULL,
 state text NOT NULL,fencing_token bigint NOT NULL,occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,brand_id,job_id) REFERENCES cos_v6.ingestion_jobs(workspace_id,brand_id,id));
CREATE TABLE cos_v6.content_replays (
 workspace_id uuid NOT NULL,brand_id uuid NOT NULL,actor_id uuid NOT NULL REFERENCES cos_v6.users,
 operation text NOT NULL,key text NOT NULL CHECK(length(key) BETWEEN 1 AND 200),request_hash bytea NOT NULL CHECK(octet_length(request_hash)=32),
 response jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,actor_id,operation,key),FOREIGN KEY(workspace_id,brand_id) REFERENCES cos_v6.brands(workspace_id,id));
CREATE TABLE cos_v6.version_registry (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),workspace_id uuid NOT NULL,brand_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind='source'),schema_version integer NOT NULL DEFAULT 1 CHECK(schema_version=1),
 snapshot jsonb NOT NULL,content_hash bytea NOT NULL CHECK(octet_length(content_hash)=32),
 sealed boolean NOT NULL DEFAULT false,sealed_at timestamptz,created_by_membership_id uuid NOT NULL,
 origin text NOT NULL CHECK(origin IN ('USER','FIXTURE')),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,brand_id,id),UNIQUE(workspace_id,brand_id,id,kind),
 FOREIGN KEY(workspace_id,brand_id) REFERENCES cos_v6.brands(workspace_id,id),
 FOREIGN KEY(workspace_id,created_by_membership_id) REFERENCES cos_v6.workspace_memberships(workspace_id,id),
 CHECK(sealed=(sealed_at IS NOT NULL)));
CREATE TABLE cos_v6.source_versions (
 id uuid PRIMARY KEY,workspace_id uuid NOT NULL,brand_id uuid NOT NULL,kind text NOT NULL DEFAULT 'source' CHECK(kind='source'),
 source_asset_id uuid NOT NULL,version_no integer NOT NULL CHECK(version_no>0),upload_id uuid NOT NULL,
 previous_version_id uuid,object_key text NOT NULL,sha256 bytea NOT NULL CHECK(octet_length(sha256)=32),size_bytes bigint NOT NULL CHECK(size_bytes>0),
 mime_type text NOT NULL,title text NOT NULL CHECK(length(title) BETWEEN 1 AND 200),rights_assertion text NOT NULL CHECK(length(rights_assertion) BETWEEN 1 AND 2000),
 UNIQUE(workspace_id,brand_id,id),UNIQUE(workspace_id,brand_id,source_asset_id,id),UNIQUE(workspace_id,brand_id,source_asset_id,version_no),
 FOREIGN KEY(workspace_id,brand_id,id,kind) REFERENCES cos_v6.version_registry(workspace_id,brand_id,id,kind),
 FOREIGN KEY(workspace_id,brand_id,source_asset_id) REFERENCES cos_v6.source_assets(workspace_id,brand_id,id),
 FOREIGN KEY(workspace_id,brand_id,upload_id) REFERENCES cos_v6.upload_intents(workspace_id,brand_id,id),
 FOREIGN KEY(workspace_id,brand_id,source_asset_id,previous_version_id) REFERENCES cos_v6.source_versions(workspace_id,brand_id,source_asset_id,id));
ALTER TABLE cos_v6.source_assets ADD CONSTRAINT source_current_fk FOREIGN KEY(workspace_id,brand_id,id,current_version_id)
 REFERENCES cos_v6.source_versions(workspace_id,brand_id,source_asset_id,id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE cos_v6.upload_intents ADD CONSTRAINT upload_completed_fk FOREIGN KEY(workspace_id,brand_id,source_asset_id,completed_source_version_id)
 REFERENCES cos_v6.source_versions(workspace_id,brand_id,source_asset_id,id) DEFERRABLE INITIALLY DEFERRED;
CREATE TABLE cos_v6.source_validation_results (
 workspace_id uuid NOT NULL,brand_id uuid NOT NULL,upload_id uuid NOT NULL,
 observed_sha256 bytea NOT NULL CHECK(octet_length(observed_sha256)=32),size_bytes bigint NOT NULL CHECK(size_bytes>0),mime_type text NOT NULL,
 scanner text NOT NULL CHECK(scanner='TEXT_POLICY_V1'),probe text NOT NULL CHECK(probe='UTF8_BOUNDS_V1'),
 job_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(workspace_id,brand_id,upload_id),FOREIGN KEY(workspace_id,brand_id,upload_id) REFERENCES cos_v6.upload_intents(workspace_id,brand_id,id),
 FOREIGN KEY(workspace_id,brand_id,job_id) REFERENCES cos_v6.ingestion_jobs(workspace_id,brand_id,id));
CREATE TABLE cos_v6.dependency_edges (
 workspace_id uuid NOT NULL,brand_id uuid NOT NULL,consumer_version_id uuid NOT NULL,prerequisite_version_id uuid NOT NULL,
 consumer_kind text NOT NULL DEFAULT 'source' CHECK(consumer_kind='source'),prerequisite_kind text NOT NULL DEFAULT 'source' CHECK(prerequisite_kind='source'),
 relation text NOT NULL DEFAULT 'revision_of' CHECK(relation='revision_of'),
 PRIMARY KEY(workspace_id,brand_id,consumer_version_id,prerequisite_version_id),CHECK(consumer_version_id<>prerequisite_version_id),
 FOREIGN KEY(workspace_id,brand_id,consumer_version_id,consumer_kind) REFERENCES cos_v6.version_registry(workspace_id,brand_id,id,kind),
 FOREIGN KEY(workspace_id,brand_id,prerequisite_version_id,prerequisite_kind) REFERENCES cos_v6.version_registry(workspace_id,brand_id,id,kind));
CREATE INDEX content_dependency_reverse ON cos_v6.dependency_edges(workspace_id,brand_id,prerequisite_version_id,consumer_version_id);

-- All private tables are forced RLS; runtime/worker have NO direct table access.
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['content_capacity','brand_graph_locks','source_assets','upload_intents','upload_parts','ingestion_jobs','ingestion_events','content_replays','version_registry','source_versions','source_validation_results','dependency_edges'] LOOP
 EXECUTE format('ALTER TABLE cos_v6.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE cos_v6.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY content_definer ON cos_v6.%I TO cos_content_owner USING(true) WITH CHECK(true)',t);
 EXECUTE format('GRANT SELECT,INSERT,UPDATE ON cos_v6.%I TO cos_content_owner',t);
 END LOOP;
END $$;

CREATE FUNCTION cos_v6.cc_immutable() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
BEGIN RAISE EXCEPTION 'IMMUTABLE_VERSION'; END $$;
CREATE TRIGGER content_validation_immutable BEFORE UPDATE OR DELETE ON cos_v6.source_validation_results FOR EACH ROW EXECUTE FUNCTION cos_v6.cc_immutable();
CREATE TRIGGER content_event_immutable BEFORE UPDATE OR DELETE ON cos_v6.ingestion_events FOR EACH ROW EXECUTE FUNCTION cos_v6.cc_immutable();
CREATE TRIGGER content_replay_immutable BEFORE UPDATE OR DELETE ON cos_v6.content_replays FOR EACH ROW EXECUTE FUNCTION cos_v6.cc_immutable();
CREATE TRIGGER content_part_immutable BEFORE UPDATE OR DELETE ON cos_v6.upload_parts FOR EACH ROW EXECUTE FUNCTION cos_v6.cc_immutable();
CREATE FUNCTION cos_v6.cc_registry_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
BEGIN
 IF TG_OP='DELETE' OR OLD.sealed THEN RAISE EXCEPTION 'IMMUTABLE_VERSION'; END IF;
 IF (to_jsonb(OLD)-ARRAY['sealed','sealed_at','content_hash'])<>(to_jsonb(NEW)-ARRAY['sealed','sealed_at','content_hash']) THEN RAISE EXCEPTION 'IMMUTABLE_VERSION'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER content_registry_guard BEFORE UPDATE OR DELETE ON cos_v6.version_registry FOR EACH ROW EXECUTE FUNCTION cos_v6.cc_registry_guard();
CREATE FUNCTION cos_v6.cc_child_guard() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE v uuid;s boolean;
BEGIN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'IMMUTABLE_VERSION'; END IF;
 IF TG_TABLE_NAME='dependency_edges' THEN v:=NEW.consumer_version_id; ELSE v:=NEW.id; END IF;
 SELECT sealed INTO s FROM cos_v6.version_registry WHERE id=v FOR UPDATE;
 IF s IS DISTINCT FROM false THEN RAISE EXCEPTION 'IMMUTABLE_VERSION'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER content_source_guard BEFORE INSERT OR UPDATE OR DELETE ON cos_v6.source_versions FOR EACH ROW EXECUTE FUNCTION cos_v6.cc_child_guard();
CREATE TRIGGER content_edge_guard BEFORE INSERT OR UPDATE OR DELETE ON cos_v6.dependency_edges FOR EACH ROW EXECUTE FUNCTION cos_v6.cc_child_guard();
CREATE FUNCTION cos_v6.cc_snapshot(v uuid) RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
 SELECT jsonb_build_object('schema_version',1,'source_asset_id',s.source_asset_id,'version_no',s.version_no,'upload_id',s.upload_id,
 'previous_version_id',s.previous_version_id,'object_key',s.object_key,'sha256',encode(s.sha256,'hex'),'size_bytes',s.size_bytes,
 'mime_type',s.mime_type,'title',s.title,'rights_assertion',s.rights_assertion) FROM cos_v6.source_versions s WHERE s.id=v
$$;
CREATE FUNCTION cos_v6.cc_total_integrity() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE v uuid;r cos_v6.version_registry;s cos_v6.source_versions;u cos_v6.upload_intents;
BEGIN
 IF TG_TABLE_NAME='dependency_edges' THEN v:=COALESCE(NEW.consumer_version_id,OLD.consumer_version_id); ELSE v:=COALESCE(NEW.id,OLD.id); END IF;
 SELECT * INTO r FROM cos_v6.version_registry WHERE id=v;
 IF NOT FOUND THEN RAISE EXCEPTION 'REGISTRY_INCOMPLETE'; END IF;
 SELECT * INTO s FROM cos_v6.source_versions WHERE id=v;
 IF NOT FOUND OR NOT r.sealed OR r.snapshot IS DISTINCT FROM cos_v6.cc_snapshot(v)
 OR r.content_hash IS DISTINCT FROM sha256(convert_to(r.snapshot::text,'UTF8')) THEN RAISE EXCEPTION 'REGISTRY_INCOMPLETE'; END IF;
 SELECT * INTO u FROM cos_v6.upload_intents WHERE id=s.upload_id;
 IF u.source_asset_id<>s.source_asset_id OR s.object_key<>u.quarantine_key OR s.sha256<>u.expected_hash OR s.size_bytes<>u.expected_size OR s.mime_type<>u.mime_type
 OR NOT EXISTS(SELECT 1 FROM cos_v6.source_validation_results x WHERE x.upload_id=u.id AND x.observed_sha256=s.sha256 AND x.size_bytes=s.size_bytes AND x.mime_type=s.mime_type)
 THEN RAISE EXCEPTION 'SOURCE_NOT_VALIDATED'; END IF;
 IF EXISTS(SELECT 1 FROM cos_v6.dependency_edges e WHERE e.consumer_version_id=v AND e.prerequisite_version_id IS DISTINCT FROM s.previous_version_id)
 OR (SELECT count(*) FROM cos_v6.dependency_edges e WHERE e.consumer_version_id=v)<>(CASE WHEN s.previous_version_id IS NULL THEN 0 ELSE 1 END)
 THEN RAISE EXCEPTION 'LINEAGE_MISMATCH'; END IF;
 IF s.previous_version_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM cos_v6.version_registry WHERE id=s.previous_version_id AND sealed) THEN RAISE EXCEPTION 'REGISTRY_INCOMPLETE'; END IF;
 IF EXISTS(WITH RECURSIVE walk(id) AS (SELECT prerequisite_version_id FROM cos_v6.dependency_edges WHERE consumer_version_id=v UNION SELECT e.prerequisite_version_id FROM cos_v6.dependency_edges e JOIN walk w ON e.consumer_version_id=w.id) SELECT 1 FROM walk WHERE id=v)
 THEN RAISE EXCEPTION 'DEPENDENCY_CYCLE'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER content_registry_total AFTER INSERT OR UPDATE OR DELETE ON cos_v6.version_registry DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cos_v6.cc_total_integrity();
CREATE CONSTRAINT TRIGGER content_source_total AFTER INSERT OR UPDATE OR DELETE ON cos_v6.source_versions DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cos_v6.cc_total_integrity();
CREATE CONSTRAINT TRIGGER content_edge_total AFTER INSERT OR UPDATE OR DELETE ON cos_v6.dependency_edges DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION cos_v6.cc_total_integrity();

CREATE FUNCTION cos_v6.cc_graph_lock(w uuid,b uuid) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN RAISE EXCEPTION 'READ_COMMITTED_REQUIRED'; END IF;
 INSERT INTO cos_v6.brand_graph_locks(workspace_id,brand_id) VALUES(w,b) ON CONFLICT DO NOTHING;
 PERFORM 1 FROM cos_v6.brand_graph_locks WHERE workspace_id=w AND brand_id=b FOR UPDATE;
END $$;
CREATE FUNCTION cos_v6.cc_construct(w uuid,b uuid,sid uuid,uid uuid,actor uuid,ttl text,rights text,previous uuid,origin_kind text) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE v uuid:=gen_random_uuid();u cos_v6.upload_intents;snap jsonb;num integer;
BEGIN
 PERFORM cos_v6.cc_graph_lock(w,b); -- separate statement BEFORE any graph query
 SELECT * INTO u FROM cos_v6.upload_intents WHERE workspace_id=w AND brand_id=b AND id=uid;
 IF NOT FOUND OR u.source_asset_id<>sid THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 IF previous IS NOT NULL AND NOT EXISTS(SELECT 1 FROM cos_v6.source_versions x JOIN cos_v6.version_registry r ON r.id=x.id WHERE x.id=previous AND x.source_asset_id=sid AND r.sealed) THEN RAISE EXCEPTION 'REGISTRY_INCOMPLETE'; END IF;
 SELECT coalesce(max(version_no),0)+1 INTO num FROM cos_v6.source_versions WHERE source_asset_id=sid;
 snap:=jsonb_build_object('schema_version',1,'source_asset_id',sid,'version_no',num,'upload_id',uid,'previous_version_id',previous,'object_key',u.quarantine_key,
 'sha256',encode(u.expected_hash,'hex'),'size_bytes',u.expected_size,'mime_type',u.mime_type,'title',ttl,'rights_assertion',rights);
 INSERT INTO cos_v6.version_registry(id,workspace_id,brand_id,kind,snapshot,content_hash,created_by_membership_id,origin)
 VALUES(v,w,b,'source',snap,sha256(convert_to(snap::text,'UTF8')),actor,origin_kind);
 INSERT INTO cos_v6.source_versions(id,workspace_id,brand_id,source_asset_id,version_no,upload_id,previous_version_id,object_key,sha256,size_bytes,mime_type,title,rights_assertion)
 VALUES(v,w,b,sid,num,uid,previous,u.quarantine_key,u.expected_hash,u.expected_size,u.mime_type,ttl,rights);
 IF previous IS NOT NULL THEN
 INSERT INTO cos_v6.dependency_edges(workspace_id,brand_id,consumer_version_id,prerequisite_version_id) VALUES(w,b,v,previous);
 END IF;
 UPDATE cos_v6.version_registry SET sealed=true,sealed_at=clock_timestamp() WHERE id=v;
 UPDATE cos_v6.source_assets SET current_version_id=v,title=ttl,revision=revision+1 WHERE id=sid;
 RETURN v;
END $$;

CREATE FUNCTION cos_v6.cc_upload_json(i uuid) RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
 SELECT jsonb_build_object('upload_id',u.id,'workspace_id',u.workspace_id,'brand_id',u.brand_id,'source_asset_id',u.source_asset_id,
 'state',u.state,'revision',u.revision,'expected_size',u.expected_size,'expected_sha256',encode(u.expected_hash,'hex'),'mime_type',u.mime_type,
 'execution_mode',u.storage_mode,'expires_at',u.expires_at,'expired',u.expires_at<=clock_timestamp(),'source_version_id',u.completed_source_version_id,'error_code',u.error_code,
 'parts',coalesce((SELECT jsonb_agg(jsonb_build_object('part_number',p.part_number,'size_bytes',p.size_bytes,'sha256',encode(p.sha256,'hex')) ORDER BY p.part_number) FROM cos_v6.upload_parts p WHERE p.upload_id=u.id),'[]'::jsonb))
 FROM cos_v6.upload_intents u WHERE u.id=i
$$;
CREATE FUNCTION cos_v6.cc_job_json(j uuid) RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
 SELECT jsonb_build_object('job_id',x.id,'workspace_id',x.workspace_id,'brand_id',x.brand_id,'upload_id',x.upload_id,'job_kind',x.job_kind,'status',x.status,
 'execution_mode','LOCAL_PRIVATE_DEVELOPMENT','paid_authority',x.paid_authority,'attempts',x.attempts,'error_code',x.error_code,
 'result_version_id',CASE WHEN x.status='SUCCEEDED' AND x.job_kind='INGEST' THEN u.completed_source_version_id ELSE NULL END,
 'events',coalesce((SELECT jsonb_agg(jsonb_build_object('state',e.state,'occurred_at',e.occurred_at,'fence',e.fencing_token) ORDER BY e.occurred_at,e.id) FROM cos_v6.ingestion_events e WHERE e.job_id=x.id),'[]'::jsonb))
 FROM cos_v6.ingestion_jobs x JOIN cos_v6.upload_intents u ON u.id=x.upload_id WHERE x.id=j
$$;
CREATE FUNCTION cos_v6.cc_read(w uuid,b uuid,kind text,target uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE result jsonb;
BEGIN
 IF b IS NULL THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 PERFORM cos_v6.api_authorize(w,b,'read');
 IF kind='upload' THEN
 IF EXISTS(SELECT 1 FROM cos_v6.upload_intents WHERE workspace_id=w AND brand_id=b AND id=target) THEN result:=cos_v6.cc_upload_json(target); END IF;
 ELSIF kind='job' THEN
 IF EXISTS(SELECT 1 FROM cos_v6.ingestion_jobs WHERE workspace_id=w AND brand_id=b AND id=target) THEN result:=cos_v6.cc_job_json(target); END IF;
 ELSIF kind='source' THEN
 SELECT jsonb_build_object('source_asset_id',s.id,'workspace_id',w,'brand_id',b,'title',s.title,'current_version_id',s.current_version_id,'revision',s.revision,
 'upload',cos_v6.cc_upload_json(u.id)) INTO result FROM cos_v6.source_assets s JOIN cos_v6.upload_intents u ON u.source_asset_id=s.id WHERE s.workspace_id=w AND s.brand_id=b AND s.id=target;
 ELSIF kind='version' THEN
 SELECT jsonb_build_object('version_id',r.id,'kind',r.kind,'sealed',r.sealed,'content_hash',encode(r.content_hash,'hex'),'snapshot',r.snapshot-'object_key',
 'origin',r.origin,'created_at',r.created_at) INTO result FROM cos_v6.version_registry r WHERE r.workspace_id=w AND r.brand_id=b AND r.id=target;
 ELSE RAISE EXCEPTION 'INVALID_INPUT'; END IF;
 IF result IS NULL THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 RETURN result;
END $$;
CREATE FUNCTION cos_v6.cc_create_upload(w uuid,b uuid,ttl text,mime text,sz bigint,h bytea,rights text,key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE actor uuid;u uuid:=gen_random_uuid();s uuid;req bytea;old cos_v6.content_replays;result jsonb;
BEGIN
 IF b IS NULL THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 actor:=cos_v6.api_authorize(w,b,'edit');
 IF key IS NULL OR length(key) NOT BETWEEN 1 AND 200 THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_REQUIRED'; END IF;
 req:=sha256(convert_to(jsonb_build_array(b,ttl,mime,sz,encode(h,'hex'),rights)::text,'UTF8'));
 SELECT * INTO old FROM cos_v6.content_replays WHERE workspace_id=w AND actor_id=cos_v6.api_actor() AND operation='createUploadIntent' AND content_replays.key=cc_create_upload.key;
 IF FOUND THEN IF old.request_hash<>req THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;RETURN old.response;END IF;
 INSERT INTO cos_v6.content_capacity(workspace_id) VALUES(w) ON CONFLICT DO NOTHING;
 PERFORM 1 FROM cos_v6.content_capacity WHERE workspace_id=w FOR UPDATE;
 IF sz IS NULL OR sz NOT BETWEEN 1 AND 2000000000 OR (SELECT reserved_bytes::numeric+sz>limit_bytes FROM cos_v6.content_capacity WHERE workspace_id=w) THEN RAISE EXCEPTION 'STORAGE_QUOTA_EXCEEDED'; END IF;
 IF (SELECT count(*) FROM cos_v6.upload_intents WHERE workspace_id=w AND state IN ('UPLOADING','QUEUED','SCANNING','BLOCKED','REJECTED','CANCELLED'))>=100 THEN RAISE EXCEPTION 'RATE_LIMITED'; END IF;
 INSERT INTO cos_v6.source_assets(workspace_id,brand_id,title,created_by_membership_id) VALUES(w,b,ttl,actor) RETURNING id INTO s;
 INSERT INTO cos_v6.upload_intents(id,workspace_id,brand_id,source_asset_id,requested_by_membership_id,quarantine_key,expected_size,expected_hash,mime_type,rights_assertion)
 VALUES(u,w,b,s,actor,w::text||'/'||b::text||'/'||u::text,sz,h,mime,rights);
 UPDATE cos_v6.content_capacity SET reserved_bytes=reserved_bytes+sz WHERE workspace_id=w;
 result:=cos_v6.cc_upload_json(u);
 INSERT INTO cos_v6.content_replays(workspace_id,brand_id,actor_id,operation,key,request_hash,response) VALUES(w,b,cos_v6.api_actor(),'createUploadIntent',key,req,result);
 RETURN result;
END $$;
CREATE FUNCTION cos_v6.cc_transfer(w uuid,b uuid,i uuid,n integer) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE u cos_v6.upload_intents;part_size bigint;
BEGIN
 IF b IS NULL THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 PERFORM cos_v6.api_authorize(w,b,'edit');
 SELECT * INTO u FROM cos_v6.upload_intents WHERE workspace_id=w AND brand_id=b AND id=i FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 IF u.state<>'UPLOADING' OR u.expires_at<=clock_timestamp() THEN RAISE EXCEPTION 'UPLOAD_NOT_WRITABLE'; END IF;
 IF n IS NULL OR n<1 OR n>ceil(u.expected_size::numeric/8388608) THEN RAISE EXCEPTION 'INVALID_PART'; END IF;
 part_size:=least(8388608,u.expected_size-(n-1)::bigint*8388608);
 RETURN jsonb_build_object('key',u.quarantine_key,'size_bytes',part_size,'revision',u.revision);
END $$;
CREATE FUNCTION cos_v6.cc_record_part(w uuid,b uuid,i uuid,n integer,sz integer,h bytea,expected bigint) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE grant_data jsonb;old cos_v6.upload_parts;
BEGIN
 grant_data:=cos_v6.cc_transfer(w,b,i,n);
 SELECT * INTO old FROM cos_v6.upload_parts WHERE upload_id=i AND part_number=n;
 IF FOUND THEN IF old.size_bytes IS DISTINCT FROM sz OR old.sha256 IS DISTINCT FROM h THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;RETURN cos_v6.cc_upload_json(i);END IF;
 IF h IS NULL OR octet_length(h)<>32 THEN RAISE EXCEPTION 'INVALID_PART'; END IF;
 IF (grant_data->>'revision')::bigint IS DISTINCT FROM expected THEN RAISE EXCEPTION 'STALE_VERSION'; END IF;
 IF sz IS DISTINCT FROM (grant_data->>'size_bytes')::integer THEN RAISE EXCEPTION 'INVALID_PART'; END IF;
 INSERT INTO cos_v6.upload_parts(workspace_id,brand_id,upload_id,part_number,size_bytes,sha256) VALUES(w,b,i,n,sz,h);
 UPDATE cos_v6.upload_intents SET revision=revision+1 WHERE id=i;
 RETURN cos_v6.cc_upload_json(i);
END $$;
CREATE FUNCTION cos_v6.cc_finalize(w uuid,b uuid,sid uuid,i uuid,expected bigint,key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE u cos_v6.upload_intents;j uuid;req bytea;old cos_v6.content_replays;result jsonb;
BEGIN
 IF b IS NULL THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;PERFORM cos_v6.api_authorize(w,b,'edit');
 IF key IS NULL OR length(key) NOT BETWEEN 1 AND 200 THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_REQUIRED'; END IF;
 req:=sha256(convert_to(jsonb_build_array(b,sid,i,expected)::text,'UTF8'));
 SELECT * INTO old FROM cos_v6.content_replays WHERE workspace_id=w AND actor_id=cos_v6.api_actor() AND operation='finalizeSource' AND content_replays.key=cc_finalize.key;
 IF FOUND THEN IF old.request_hash<>req THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;RETURN old.response;END IF;
 SELECT * INTO u FROM cos_v6.upload_intents WHERE workspace_id=w AND brand_id=b AND id=i AND source_asset_id=sid FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 IF u.revision IS DISTINCT FROM expected THEN RAISE EXCEPTION 'STALE_VERSION'; END IF;
 IF u.state<>'UPLOADING' OR u.expires_at<=clock_timestamp() THEN RAISE EXCEPTION 'UPLOAD_NOT_WRITABLE'; END IF;
 IF (SELECT coalesce(sum(size_bytes),0) FROM cos_v6.upload_parts WHERE upload_id=i)<>u.expected_size THEN RAISE EXCEPTION 'UPLOAD_INCOMPLETE'; END IF;
 UPDATE cos_v6.upload_intents SET state='QUEUED',revision=revision+1 WHERE id=i;
 INSERT INTO cos_v6.ingestion_jobs(workspace_id,brand_id,upload_id,job_kind) VALUES(w,b,i,'INGEST') RETURNING id INTO j;
 INSERT INTO cos_v6.ingestion_events(workspace_id,brand_id,job_id,state,fencing_token) VALUES(w,b,j,'QUEUED',0);
 result:=jsonb_build_object('job_id',j,'state','QUEUED','upload_id',i,'revision',u.revision+1);
 INSERT INTO cos_v6.content_replays(workspace_id,brand_id,actor_id,operation,key,request_hash,response) VALUES(w,b,cos_v6.api_actor(),'finalizeSource',key,req,result);
 RETURN result;
END $$;
CREATE FUNCTION cos_v6.cc_cancel(w uuid,b uuid,i uuid,expected bigint) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE u cos_v6.upload_intents;j uuid;
BEGIN
 IF b IS NULL THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;PERFORM cos_v6.api_authorize(w,b,'edit');
 SELECT * INTO u FROM cos_v6.upload_intents WHERE workspace_id=w AND brand_id=b AND id=i FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 IF u.revision IS DISTINCT FROM expected THEN RAISE EXCEPTION 'STALE_VERSION'; END IF;
 IF u.state IN ('CLEARED','PURGED') THEN RAISE EXCEPTION 'UPLOAD_NOT_WRITABLE'; END IF;
 UPDATE cos_v6.upload_intents SET state='CANCELLED',revision=revision+1 WHERE id=i;
 UPDATE cos_v6.ingestion_jobs SET status='CANCELLED',claim_hash=NULL,claimed_by=NULL,lease_expires_at=NULL,fencing_token=fencing_token+1 WHERE upload_id=i AND job_kind='INGEST' AND status<>'SUCCEEDED';
 INSERT INTO cos_v6.ingestion_events(workspace_id,brand_id,job_id,state,fencing_token) SELECT w,b,id,status,fencing_token FROM cos_v6.ingestion_jobs WHERE upload_id=i AND job_kind='INGEST';
 INSERT INTO cos_v6.ingestion_jobs(workspace_id,brand_id,upload_id,job_kind) VALUES(w,b,i,'PURGE_CANCELLED_UPLOAD') ON CONFLICT DO NOTHING RETURNING id INTO j;
 IF j IS NOT NULL THEN INSERT INTO cos_v6.ingestion_events(workspace_id,brand_id,job_id,state,fencing_token) VALUES(w,b,j,'QUEUED',0); END IF;
 RETURN cos_v6.cc_upload_json(i);
END $$;
CREATE FUNCTION cos_v6.cc_revise(w uuid,b uuid,sid uuid,ttl text,rights text,expected bigint,key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE s cos_v6.source_assets;u cos_v6.upload_intents;actor uuid;v uuid;old cos_v6.content_replays;req bytea;result jsonb;
BEGIN
 IF b IS NULL THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;actor:=cos_v6.api_authorize(w,b,'edit');
 IF key IS NULL OR length(key) NOT BETWEEN 1 AND 200 THEN RAISE EXCEPTION 'IDEMPOTENCY_KEY_REQUIRED'; END IF;
 req:=sha256(convert_to(jsonb_build_array(b,sid,ttl,rights,expected)::text,'UTF8'));
 SELECT * INTO old FROM cos_v6.content_replays WHERE workspace_id=w AND actor_id=cos_v6.api_actor() AND operation='reviseSourceMetadata' AND content_replays.key=cc_revise.key;
 IF FOUND THEN IF old.request_hash<>req THEN RAISE EXCEPTION 'IDEMPOTENCY_CONFLICT'; END IF;RETURN old.response;END IF;
 SELECT * INTO s FROM cos_v6.source_assets WHERE workspace_id=w AND brand_id=b AND id=sid FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 IF s.revision IS DISTINCT FROM expected THEN RAISE EXCEPTION 'STALE_VERSION'; END IF;
 SELECT * INTO u FROM cos_v6.upload_intents WHERE source_asset_id=sid;
 IF u.state<>'CLEARED' OR s.current_version_id IS NULL THEN RAISE EXCEPTION 'QUARANTINED'; END IF;
 v:=cos_v6.cc_construct(w,b,sid,u.id,actor,ttl,rights,s.current_version_id,'USER');
 result:=jsonb_build_object('source_asset_id',sid,'version_id',v,'revision',s.revision+1);
 INSERT INTO cos_v6.content_replays(workspace_id,brand_id,actor_id,operation,key,request_hash,response) VALUES(w,b,cos_v6.api_actor(),'reviseSourceMetadata',key,req,result);
 RETURN result;
END $$;
CREATE FUNCTION cos_v6.cc_download(w uuid,b uuid,sid uuid,v uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE s cos_v6.source_versions;u cos_v6.upload_intents;
BEGIN
 IF b IS NULL THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;PERFORM cos_v6.api_authorize(w,b,'read');
 SELECT * INTO s FROM cos_v6.source_versions WHERE workspace_id=w AND brand_id=b AND id=v AND source_asset_id=sid;
 IF NOT FOUND THEN RAISE EXCEPTION 'NOT_FOUND'; END IF;
 SELECT * INTO u FROM cos_v6.upload_intents WHERE id=s.upload_id;
 IF u.state<>'CLEARED' OR NOT EXISTS(SELECT 1 FROM cos_v6.source_validation_results WHERE upload_id=u.id) THEN RAISE EXCEPTION 'QUARANTINED'; END IF;
 RETURN jsonb_build_object('key',s.object_key,'size_bytes',s.size_bytes,'sha256',encode(s.sha256,'hex'),'mime_type',s.mime_type,
 'parts',(SELECT jsonb_agg(jsonb_build_object('part_number',part_number,'size_bytes',size_bytes,'sha256',encode(sha256,'hex')) ORDER BY part_number) FROM cos_v6.upload_parts WHERE upload_id=u.id));
END $$;

-- Queue-specific worker functions: opaque random claim capability, session_user binding,
-- fencing, expiry and same-tenant records. No impersonation/session/foundation bridge.
CREATE FUNCTION cos_v6.cc_worker_authorized(w uuid,b uuid,m uuid) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN RAISE EXCEPTION 'READ_COMMITTED_REQUIRED'; END IF;
 PERFORM 1 FROM cos_v6.workspaces WHERE id=w FOR UPDATE;
 RETURN EXISTS(SELECT 1 FROM cos_v6.workspace_memberships x JOIN cos_v6.workspaces t ON t.id=x.workspace_id JOIN cos_v6.users u ON u.id=x.user_id
 WHERE x.workspace_id=w AND x.id=m AND x.state='ACTIVE' AND t.state='ACTIVE' AND u.status='ACTIVE' AND u.verified_at IS NOT NULL
 AND EXISTS(SELECT 1 FROM cos_v6.user_identities WHERE user_id=u.id)
 AND EXISTS(SELECT 1 FROM cos_v6.brands z WHERE z.workspace_id=w AND z.id=b AND z.state='ACTIVE')
 AND (t.owner_membership_id=x.id OR x.roles && ARRAY['admin','editor']::text[] AND EXISTS(SELECT 1 FROM cos_v6.brand_grants g WHERE g.workspace_id=w AND g.brand_id=b AND g.membership_id=x.id AND g.state='ACTIVE')));
END $$;
CREATE FUNCTION cos_v6.cc_claim(w uuid,b uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE j cos_v6.ingestion_jobs;u cos_v6.upload_intents;cap text;allowed boolean;
BEGIN
 IF w IS NULL OR b IS NULL OR current_setting('transaction_isolation')<>'read committed' THEN RAISE EXCEPTION 'INVALID_INPUT'; END IF;
 PERFORM 1 FROM cos_v6.workspaces WHERE id=w FOR UPDATE;
 SELECT * INTO j FROM cos_v6.ingestion_jobs WHERE workspace_id=w AND brand_id=b AND (status='QUEUED' OR status='RUNNING' AND lease_expires_at<=clock_timestamp()) ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT * INTO u FROM cos_v6.upload_intents WHERE id=j.upload_id FOR UPDATE;
 allowed:=CASE WHEN j.job_kind='INGEST' THEN cos_v6.cc_worker_authorized(w,b,u.requested_by_membership_id) AND u.state IN ('QUEUED','SCANNING') ELSE u.state='CANCELLED' END;
 IF NOT allowed OR j.attempts>=3 THEN
 UPDATE cos_v6.ingestion_jobs SET status='BLOCKED',error_code=CASE WHEN NOT allowed THEN 'AUTHORITY_REVOKED' ELSE 'ATTEMPTS_EXHAUSTED' END,claim_hash=NULL,claimed_by=NULL,lease_expires_at=NULL,fencing_token=fencing_token+1 WHERE id=j.id;
 IF j.job_kind='INGEST' THEN UPDATE cos_v6.upload_intents SET state='BLOCKED',error_code=CASE WHEN NOT allowed THEN 'AUTHORITY_REVOKED' ELSE 'ATTEMPTS_EXHAUSTED' END,revision=revision+1 WHERE id=u.id;END IF;
 INSERT INTO cos_v6.ingestion_events(workspace_id,brand_id,job_id,state,fencing_token) VALUES(w,b,j.id,'BLOCKED',j.fencing_token+1);
 RETURN jsonb_build_object('job_id',j.id,'status','BLOCKED');
 END IF;
 cap:=gen_random_uuid()::text||gen_random_uuid()::text;
 UPDATE cos_v6.ingestion_jobs SET status='RUNNING',claim_hash=sha256(convert_to(cap,'UTF8')),claimed_by=session_user,lease_expires_at=clock_timestamp()+interval '60 seconds',fencing_token=fencing_token+1,attempts=attempts+1 WHERE id=j.id RETURNING * INTO j;
 IF j.job_kind='INGEST' THEN UPDATE cos_v6.upload_intents SET state='SCANNING',revision=revision+1 WHERE id=u.id; END IF;
 INSERT INTO cos_v6.ingestion_events(workspace_id,brand_id,job_id,state,fencing_token) VALUES(w,b,j.id,'RUNNING',j.fencing_token);
 RETURN jsonb_build_object('job_id',j.id,'status','RUNNING','job_kind',j.job_kind,'claim',cap,'fence',j.fencing_token,'key',u.quarantine_key,
 'expected_size',u.expected_size,'expected_sha256',encode(u.expected_hash,'hex'),'mime_type',u.mime_type,
 'parts',(SELECT jsonb_agg(jsonb_build_object('part_number',part_number,'size_bytes',size_bytes,'sha256',encode(sha256,'hex')) ORDER BY part_number) FROM cos_v6.upload_parts WHERE upload_id=u.id));
END $$;
CREATE FUNCTION cos_v6.cc_fenced(w uuid,b uuid,jid uuid,cap text,fence bigint) RETURNS cos_v6.ingestion_jobs LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE j cos_v6.ingestion_jobs;u cos_v6.upload_intents;
BEGIN
 IF current_setting('transaction_isolation')<>'read committed' THEN RAISE EXCEPTION 'READ_COMMITTED_REQUIRED'; END IF;
 PERFORM 1 FROM cos_v6.workspaces WHERE id=w FOR UPDATE;
 SELECT * INTO j FROM cos_v6.ingestion_jobs WHERE workspace_id=w AND brand_id=b AND id=jid FOR UPDATE;
 IF NOT FOUND OR j.status<>'RUNNING' OR j.claimed_by<>session_user OR j.fencing_token IS DISTINCT FROM fence OR j.claim_hash IS DISTINCT FROM sha256(convert_to(cap,'UTF8')) OR j.lease_expires_at<=clock_timestamp() THEN RAISE EXCEPTION 'STALE_CLAIM'; END IF;
 SELECT * INTO u FROM cos_v6.upload_intents WHERE id=j.upload_id FOR UPDATE;
 IF j.job_kind='INGEST' AND (u.state<>'SCANNING' OR NOT cos_v6.cc_worker_authorized(w,b,u.requested_by_membership_id)) THEN RAISE EXCEPTION 'AUTHORITY_REVOKED'; END IF;
 IF j.job_kind='PURGE_CANCELLED_UPLOAD' AND u.state<>'CANCELLED' THEN RAISE EXCEPTION 'STALE_CLAIM'; END IF;
 RETURN j;
END $$;
CREATE FUNCTION cos_v6.cc_heartbeat(w uuid,b uuid,jid uuid,cap text,fence bigint) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
BEGIN
 PERFORM cos_v6.cc_fenced(w,b,jid,cap,fence);
 UPDATE cos_v6.ingestion_jobs SET lease_expires_at=clock_timestamp()+interval '60 seconds' WHERE id=jid;
END $$;
CREATE FUNCTION cos_v6.cc_finish(w uuid,b uuid,jid uuid,cap text,fence bigint,outcome text,h bytea,sz bigint,mime text,scanner text,probe text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,cos_v6 AS $$
DECLARE j cos_v6.ingestion_jobs;u cos_v6.upload_intents;v uuid;next_state text;code text;
BEGIN
 j:=cos_v6.cc_fenced(w,b,jid,cap,fence);
 SELECT * INTO u FROM cos_v6.upload_intents WHERE id=j.upload_id;
 IF j.job_kind='PURGE_CANCELLED_UPLOAD' THEN
 IF outcome IS DISTINCT FROM 'PURGED' THEN RAISE EXCEPTION 'INVALID_INPUT'; END IF;
 UPDATE cos_v6.upload_intents SET state='PURGED',revision=revision+1 WHERE id=u.id;
 UPDATE cos_v6.content_capacity SET reserved_bytes=reserved_bytes-u.expected_size WHERE workspace_id=w;
 next_state:='SUCCEEDED';
 ELSE
 IF outcome='CLEAR' THEN
 IF h IS DISTINCT FROM u.expected_hash OR sz IS DISTINCT FROM u.expected_size OR mime IS DISTINCT FROM u.mime_type THEN RAISE EXCEPTION 'VALIDATION_MISMATCH'; END IF;
 IF mime IS DISTINCT FROM 'text/plain' THEN RAISE EXCEPTION 'SCANNER_UNCONFIGURED'; END IF;
 IF scanner IS DISTINCT FROM 'TEXT_POLICY_V1' OR probe IS DISTINCT FROM 'UTF8_BOUNDS_V1' THEN RAISE EXCEPTION 'SCANNER_UNCONFIGURED'; END IF;
 INSERT INTO cos_v6.source_validation_results(workspace_id,brand_id,upload_id,observed_sha256,size_bytes,mime_type,scanner,probe,job_id) VALUES(w,b,u.id,h,sz,mime,scanner,probe,jid);
 v:=cos_v6.cc_construct(w,b,u.source_asset_id,u.id,u.requested_by_membership_id,(SELECT title FROM cos_v6.source_assets WHERE id=u.source_asset_id),u.rights_assertion,NULL,'USER');
 UPDATE cos_v6.upload_intents SET state='CLEARED',completed_source_version_id=v,revision=revision+1 WHERE id=u.id;
 next_state:='SUCCEEDED';
 ELSIF outcome IN ('SCANNER_UNCONFIGURED','STORAGE_UNCONFIGURED') THEN next_state:='BLOCKED';code:=outcome;
 ELSIF outcome IN ('HASH_MISMATCH','MIME_MISMATCH','SIZE_MISMATCH','SCAN_REJECTED','PROBE_REJECTED','STORAGE_INVALID','PROCESSING_LIMIT') THEN next_state:='REJECTED';code:=outcome;
 ELSE RAISE EXCEPTION 'INVALID_INPUT';END IF;
 IF code IS NOT NULL THEN UPDATE cos_v6.upload_intents SET state=next_state,error_code=code,revision=revision+1 WHERE id=u.id; END IF;
 END IF;
 UPDATE cos_v6.ingestion_jobs SET status=next_state,error_code=code,claim_hash=NULL,lease_expires_at=NULL,claimed_by=NULL WHERE id=jid;
 INSERT INTO cos_v6.ingestion_events(workspace_id,brand_id,job_id,state,fencing_token) VALUES(w,b,jid,next_state,fence);
 RETURN cos_v6.cc_job_json(jid);
END $$;

-- Explicit per-routine revocation, never global default ACL mutation.
DO $$ DECLARE sig text; BEGIN
 FOREACH sig IN ARRAY ARRAY[
 'cc_immutable()','cc_registry_guard()','cc_child_guard()','cc_snapshot(uuid)','cc_total_integrity()',
 'cc_graph_lock(uuid,uuid)','cc_construct(uuid,uuid,uuid,uuid,uuid,text,text,uuid,text)',
 'cc_upload_json(uuid)','cc_job_json(uuid)','cc_read(uuid,uuid,text,uuid)',
 'cc_create_upload(uuid,uuid,text,text,bigint,bytea,text,text)','cc_transfer(uuid,uuid,uuid,integer)',
 'cc_record_part(uuid,uuid,uuid,integer,integer,bytea,bigint)','cc_finalize(uuid,uuid,uuid,uuid,bigint,text)',
 'cc_cancel(uuid,uuid,uuid,bigint)','cc_revise(uuid,uuid,uuid,text,text,bigint,text)','cc_download(uuid,uuid,uuid,uuid)',
 'cc_worker_authorized(uuid,uuid,uuid)','cc_claim(uuid,uuid)','cc_fenced(uuid,uuid,uuid,text,bigint)',
 'cc_heartbeat(uuid,uuid,uuid,text,bigint)','cc_finish(uuid,uuid,uuid,text,bigint,text,bytea,bigint,text,text,text)'] LOOP
 EXECUTE 'REVOKE ALL ON FUNCTION cos_v6.'||sig||' FROM PUBLIC';
 EXECUTE 'ALTER FUNCTION cos_v6.'||sig||' OWNER TO cos_content_owner';
 END LOOP;
END $$;
GRANT EXECUTE ON FUNCTION cos_v6.cc_read(uuid,uuid,text,uuid),cos_v6.cc_create_upload(uuid,uuid,text,text,bigint,bytea,text,text),
 cos_v6.cc_transfer(uuid,uuid,uuid,integer),cos_v6.cc_record_part(uuid,uuid,uuid,integer,integer,bytea,bigint),
 cos_v6.cc_finalize(uuid,uuid,uuid,uuid,bigint,text),cos_v6.cc_cancel(uuid,uuid,uuid,bigint),
 cos_v6.cc_revise(uuid,uuid,uuid,text,text,bigint,text),cos_v6.cc_download(uuid,uuid,uuid,uuid) TO cos_api_runtime;
GRANT EXECUTE ON FUNCTION cos_v6.cc_claim(uuid,uuid),cos_v6.cc_heartbeat(uuid,uuid,uuid,text,bigint),
 cos_v6.cc_finish(uuid,uuid,uuid,text,bigint,text,bytea,bigint,text,text,text) TO cos_content_worker;
