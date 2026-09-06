# Architecture and domain rules

The browser → Nginx → FastAPI path is the public application surface. Nginx also performs
an auth subrequest before proxying read-only `/gis/` requests to pygeoapi. PostGIS stores
normalized events, source evidence, assets, revisions, alerts, credentials and a durable queue.
No Redis or external cloud model is required. Static UI assets and fonts are bundled locally.

## Transactions and concurrency

The collection worker claims jobs using `FOR UPDATE SKIP LOCKED`, with a 20-minute lease,
up to five attempts, and bounded exponential retry. Collection checkpoints commit with the
normalized events and raw payloads. Failed batches do not advance checkpoints. Expired leases
are reclaimed after restart; collection upserts and webhook delivery IDs are idempotent.

A transaction-level advisory lock serializes event mutations with change sequence assignment.
This prevents a later cursor being committed ahead of an earlier event mutation. Snapshot +
change replay tolerates duplicates. Changes retain upsert snapshots and deletion tombstones.
Geospatial indexes cover geometry bbox and geography distance queries. Proximity uses meters
on geography; display geometries are WGS84. USGS depth is retained in raw data while the map
geometry is forced to 2D.

AI/enrichment jobs run on a separate worker and cannot block the collection worker. Inference
uses a configurable local endpoint, a bounded prompt/context, structured output and an ID
allowlist for evidence citations. Citation validation proves references exist, not that every
model sentence follows logically; summaries remain labeled and reviewable suggestions.

## Exposure and uncertainty

Per-asset rules combine category, minimum severity, polygon intersection, and distance to an
asset point or polygon. This is an explainable proximity signal, not predicted damage. Source
severity and source confidence are separate. News locations and epicenters are approximate.
Null/invalid locations never become fabricated map points. Candidate cross-source matches
require the same category, one-hour occurrence proximity, and ten-kilometer distance. They
remain separate records; matching does not establish corroboration.

Acknowledgment persists while exposure remains. Expired/cancelled/out-of-rule events resolve
alerts. Reappearing exposure reopens a resolved alert. Assets can be edited or removed;
removing an asset cascades only its alerts. Import validation is all-or-nothing.

## Security boundary

This release is one local administrator/workspace, not enterprise multi-tenancy. API tokens
are random, hashed at rest, scoped, expiring and revocable. Sessions use HttpOnly cookies and
Origin checks. Secrets stay out of HTTP access logs and the frontend's persistent storage.
User text and feed text are rendered as text, never HTML. No arbitrary shell/module selection
is exposed through enrichment. Administrative operations are recorded in audit_log.

Source export policy is applied to REST, vector tiles, OGC SQL view, exposure, summaries and
webhook delivery. The GIS container has no public port. Keep the default network boundary;
exposing it directly would bypass the gateway. User-defined outbound URLs reject non-public
DNS addresses unless explicitly allowlisted. Redirects are disabled. For hostile multi-user
installations, add a network egress proxy/firewall that pins/resolves allowed destinations;
application DNS prevalidation alone is not protection against DNS rebinding.

The default bind is loopback. For LAN/public deployments use TLS, accurate WATCH_PUBLIC_URL,
secure cookies, and network restrictions. Basemap requests reach the configured external map
provider and reveal the viewed region; point/area assets remain in the local database.

## Retention and limitations

Defaults: raw payloads seven days; inactive normalized records, changes and completed jobs
90 days. Active events persist until expiry. Restore procedures never overwrite a running
workspace. Longer GDELT outages exceed the bounded catch-up window and need a separate
historical backfill. The application does not promise complete or instantaneous source coverage.
Enterprise SSO, moving assets, WMS and paid datasets are intentionally deferred.
