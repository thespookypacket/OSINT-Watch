CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE sources (
    id text PRIMARY KEY, name text NOT NULL, adapter text NOT NULL, url text NOT NULL,
    category text NOT NULL, attribution text NOT NULL, export_allowed boolean NOT NULL DEFAULT false,
    enabled boolean NOT NULL DEFAULT true, interval_seconds int NOT NULL DEFAULT 900,
    config jsonb NOT NULL DEFAULT '{}', checkpoint jsonb NOT NULL DEFAULT '{}',
    last_attempt timestamptz, last_success timestamptz, last_error text,
    rejected_count int NOT NULL DEFAULT 0, event_count int NOT NULL DEFAULT 0,
    next_run timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), source_id text NOT NULL REFERENCES sources(id),
    external_id text NOT NULL, title text NOT NULL, category text NOT NULL, severity int NOT NULL,
    source_severity text NOT NULL, status text NOT NULL, occurred_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL, ingested_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz,
    geom geometry(Geometry,4326), precision text NOT NULL, evidence_url text NOT NULL,
    description text NOT NULL, confidence text NOT NULL, properties jsonb NOT NULL,
    fingerprint text NOT NULL, UNIQUE(source_id,external_id)
);
CREATE INDEX events_geom ON events USING gist(geom);
CREATE INDEX events_geography ON events USING gist((geom::geography));
CREATE INDEX events_time ON events(updated_at DESC, id);
CREATE INDEX events_category ON events(category,status);
CREATE TABLE changes (
    seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, event_id uuid NOT NULL,
    source_id text NOT NULL REFERENCES sources(id), operation text NOT NULL,
    feature jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX changes_event ON changes(event_id,seq DESC);
CREATE TABLE sync_state (singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), floor bigint NOT NULL DEFAULT 0);
INSERT INTO sync_state VALUES (true,0);
CREATE TABLE raw_payloads (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id text REFERENCES sources(id), fetched_at timestamptz NOT NULL DEFAULT now(), payload jsonb NOT NULL);
CREATE TABLE event_links (event_a uuid REFERENCES events(id) ON DELETE CASCADE,
    event_b uuid REFERENCES events(id) ON DELETE CASCADE, reason text NOT NULL,
    PRIMARY KEY(event_a,event_b), CHECK(event_a < event_b));
CREATE TABLE assets (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL,
    geom geometry(Geometry,4326) NOT NULL, radius_km double precision NOT NULL DEFAULT 25,
    min_severity int NOT NULL DEFAULT 2, categories text[] NOT NULL, domains text[] NOT NULL DEFAULT '{}',
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX assets_geom ON assets USING gist(geom);
CREATE TABLE alerts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), event_id uuid NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    reason text NOT NULL, distance_km double precision NOT NULL, status text NOT NULL DEFAULT 'open',
    acknowledged_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(event_id,asset_id)
);
CREATE TABLE credentials (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL,
    digest text NOT NULL UNIQUE, scopes text[] NOT NULL, kind text NOT NULL DEFAULT 'api',
    expires_at timestamptz NOT NULL, revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE users (username text PRIMARY KEY, password_hash text NOT NULL);
CREATE TABLE webhooks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text NOT NULL, url text NOT NULL,
    secret text NOT NULL, enabled boolean NOT NULL DEFAULT true
);
CREATE TABLE jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(), kind text NOT NULL, payload jsonb NOT NULL,
    dedup_key text UNIQUE, status text NOT NULL DEFAULT 'pending', attempts int NOT NULL DEFAULT 0,
    available_at timestamptz NOT NULL DEFAULT now(), leased_until timestamptz,
    result jsonb, error text, created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
CREATE INDEX jobs_pending ON jobs(status,available_at);
CREATE TABLE audit_log (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor text NOT NULL, action text NOT NULL, object_id text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE rate_limits (key text PRIMARY KEY, window_at timestamptz NOT NULL DEFAULT now(), count int NOT NULL);
CREATE TABLE worker_health (id text PRIMARY KEY, heartbeat timestamptz NOT NULL);

CREATE VIEW export_events AS SELECT e.id::text AS id,e.geom,e.title,e.category,e.severity,
    e.status,e.occurred_at,e.updated_at,e.precision,e.evidence_url,e.source_id,s.attribution
    FROM events e JOIN sources s ON s.id=e.source_id WHERE s.export_allowed;
