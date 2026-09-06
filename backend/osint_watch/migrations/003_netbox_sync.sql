ALTER TABLE assets ADD COLUMN external_source text;
ALTER TABLE assets ADD COLUMN external_instance text;
ALTER TABLE assets ADD COLUMN external_id text;
ALTER TABLE assets ADD COLUMN sync_state text CHECK (sync_state IN ('current','missing','unlocated'));
ALTER TABLE assets ADD COLUMN last_synced_at timestamptz;
CREATE UNIQUE INDEX assets_external ON assets(external_source,external_instance,external_id);
CREATE TABLE integration_sync (
    id text PRIMARY KEY, last_attempt timestamptz, last_success timestamptz,
    next_run timestamptz NOT NULL DEFAULT now(), last_error text, result jsonb
);
INSERT INTO integration_sync(id) VALUES ('netbox');
