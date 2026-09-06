# Operations

Run `docker compose ps` for container state. `/health` validates API database access.
Sources displays per-feed status, last success, rejected count, and configuration failures.
The collection worker has a heartbeat healthcheck; Jobs shows durable failure/retry states.
`docker compose logs --tail 100 worker` returns structured job errors without provider URLs
or secrets. Nginx is the only publicly bound service.

## Backup and restore

```sh
python3 scripts/backup.py backups/watch.dump
python3 scripts/restore.py backups/watch.dump --database watch_restore_check
```

Backup uses a consistent PostgreSQL custom-format dump and mode 0600. Back up `.env` and
`config/` separately using your secure backup system. Dumps contain asset locations, raw source
records, token digests and webhook signing secrets. Protect them accordingly.

Restore always creates a **new** database, refuses existing databases and never drops the
operator workspace. Validate restored event/asset counts and source configuration before a
manual application cutover. The default Compose database URL targets `watch`; use a Compose
override to point API and both workers at your restored database, and update the GIS dbname
configuration before cutover. Keep the original database until validation is complete.

## Upgrade and recovery

Back up first. Build the chosen revision and run `docker compose up -d --build`. SQL migrations
are ordered files with a schema_migrations ledger and advisory lock. Existing source pause
settings and credentials survive. Failed source jobs retry up to five times; a later scheduled
collection can recover. Use Sources → Refresh after repairing configuration.

If a worker crashes mid-batch, the transaction rolls back. A running job is reclaimed when its
20-minute lease expires. Webhook consumers must deduplicate delivery IDs, because delivery can
succeed remotely before the local transaction records completion.

To pause ingestion without deleting data: `docker compose stop worker`. To stop the stack:
`docker compose stop`. Never use `docker compose down -v` unless intentionally deleting all data.

## Optional integrations

FIRMS: obtain a free map key, set WATCH_FIRMS_KEY, restart the worker. No paid subscription is
required. Other default feeds need no credentials. Local AI model installation is separate;
a missing endpoint/model is visible as a failed job and cannot stop feed collection.

SpiderFoot runs behind a private authenticated bridge, with upstream passive module selection,
no arbitrary arguments, a fixed timeout and bounded output. Do not expose its port externally.
The deployment uses upstream v4.0 with PyYAML 6.0.3 to keep its dependency build compatible; review upstream changes before updating this independent tool.
