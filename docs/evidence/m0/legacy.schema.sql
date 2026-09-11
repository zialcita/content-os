-- SQLAlchemy source-compiled PostgreSQL DDL; not an applied migration.

CREATE TABLE workspaces (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	api_key_hash VARCHAR(64) NOT NULL, 
	api_key_prefix VARCHAR(16) NOT NULL, 
	spend_usd FLOAT NOT NULL, 
	spend_limit_usd FLOAT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
)

;

CREATE TABLE audit_logs (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	actor VARCHAR(120) NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	entity_type VARCHAR(64) NOT NULL, 
	entity_id VARCHAR(36) NOT NULL, 
	payload JSON NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;

CREATE TABLE avatar_profiles (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	provider VARCHAR(32) NOT NULL, 
	provider_avatar_id VARCHAR(200) NOT NULL, 
	settings JSON NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;

CREATE TABLE brands (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	voice TEXT NOT NULL, 
	guidelines TEXT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;

CREATE TABLE media_assets (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(32) NOT NULL, 
	source VARCHAR(32) NOT NULL, 
	uri VARCHAR(2000) NOT NULL, 
	title VARCHAR(300) NOT NULL, 
	metadata JSON NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;

CREATE TABLE research_sources (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	url VARCHAR(2000) NOT NULL, 
	source_type VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;

CREATE TABLE users (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	email VARCHAR(320) NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	role VARCHAR(32) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_ws_email UNIQUE (workspace_id, email), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;

CREATE TABLE evidence_items (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	source_id VARCHAR(36) NOT NULL, 
	title VARCHAR(400) NOT NULL, 
	content TEXT NOT NULL, 
	url VARCHAR(2000) NOT NULL, 
	embedding JSON, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id), 
	FOREIGN KEY(source_id) REFERENCES research_sources (id)
)

;

CREATE TABLE personas (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	brand_id VARCHAR(36), 
	name VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	tone VARCHAR(200) NOT NULL, 
	audience VARCHAR(200) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id), 
	FOREIGN KEY(brand_id) REFERENCES brands (id)
)

;

CREATE TABLE video_projects (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	brand_id VARCHAR(36), 
	persona_id VARCHAR(36), 
	avatar_id VARCHAR(36), 
	title VARCHAR(300) NOT NULL, 
	topic TEXT NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	script_draft TEXT NOT NULL, 
	script_final TEXT NOT NULL, 
	youtube_video_id VARCHAR(64) NOT NULL, 
	published_url VARCHAR(2000) NOT NULL, 
	error TEXT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id), 
	FOREIGN KEY(brand_id) REFERENCES brands (id), 
	FOREIGN KEY(persona_id) REFERENCES personas (id), 
	FOREIGN KEY(avatar_id) REFERENCES avatar_profiles (id)
)

;

CREATE TABLE clips (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	video_id VARCHAR(36) NOT NULL, 
	asset_id VARCHAR(36), 
	title VARCHAR(300) NOT NULL, 
	start_s FLOAT NOT NULL, 
	end_s FLOAT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id), 
	FOREIGN KEY(video_id) REFERENCES video_projects (id), 
	FOREIGN KEY(asset_id) REFERENCES media_assets (id)
)

;

CREATE TABLE cost_ledger (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	video_id VARCHAR(36), 
	provider VARCHAR(32) NOT NULL, 
	operation VARCHAR(80) NOT NULL, 
	amount_usd FLOAT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id), 
	FOREIGN KEY(video_id) REFERENCES video_projects (id)
)

;

CREATE TABLE render_jobs (
	id VARCHAR(36) NOT NULL, 
	workspace_id VARCHAR(36) NOT NULL, 
	video_id VARCHAR(36), 
	job_type VARCHAR(32) NOT NULL, 
	provider VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	external_id VARCHAR(200) NOT NULL, 
	result_payload JSON NOT NULL, 
	error TEXT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id), 
	FOREIGN KEY(video_id) REFERENCES video_projects (id)
)

;

CREATE TABLE video_scenes (
	id VARCHAR(36) NOT NULL, 
	video_id VARCHAR(36) NOT NULL, 
	idx INTEGER NOT NULL, 
	script_text TEXT NOT NULL, 
	visual_direction TEXT NOT NULL, 
	aroll_asset_id VARCHAR(36), 
	broll_asset_id VARCHAR(36), 
	PRIMARY KEY (id), 
	FOREIGN KEY(video_id) REFERENCES video_projects (id), 
	FOREIGN KEY(aroll_asset_id) REFERENCES media_assets (id), 
	FOREIGN KEY(broll_asset_id) REFERENCES media_assets (id)
)

;