DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='watch_gis') THEN
        CREATE ROLE watch_gis LOGIN;
    END IF;
END $$;
ALTER ROLE watch_gis SET default_transaction_read_only=on;
GRANT USAGE ON SCHEMA public TO watch_gis;
GRANT SELECT ON export_events,geometry_columns,spatial_ref_sys TO watch_gis;
