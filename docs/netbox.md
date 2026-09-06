# NetBox site synchronization

OSINT Watch imports **NetBox sites** as saved Point assets, using the site's latitude and
longitude. It never geocodes an address or guesses a device location, and it never writes to
NetBox. All sites visible to the configured token are included, regardless of site status.

## Configure

Add these settings to `.env`:

```dotenv
WATCH_NETBOX_URL=https://netbox.example.com
WATCH_NETBOX_TOKEN=your-read-only-token
WATCH_NETBOX_INTERVAL_SECONDS=3600
```

Use the NetBox application base URL; subpaths and a trailing `/api/` are supported. A private
LAN endpoint is allowed because this is an operator-configured integration. Inside Docker,
`localhost` means the container; use your server's reachable hostname instead. TLS certificate
verification stays enabled. Mount your organization's CA and set SSL_CERT_FILE if needed.

The token needs permission to view sites and does not need write permission. Legacy tokens
use `Authorization: Token`; `nbt_` v2 tokens use `Authorization: Bearer` automatically. The
secret remains in deployment configuration; it is never returned by the application API.

Apply configuration or token changes by **recreating**, rather than merely restarting, services:

```sh
docker compose up -d --build api worker web
```

If you explicitly override WATCH_JOB_KINDS, include `netbox` on the collection worker. The
separate enrichment worker does not need it. Default sync is hourly. Set the interval to `0`
for manual-only sync (positive intervals below 60 seconds are clamped to one minute).

Open **Saved assets → NetBox sites → Sync from NetBox**. The panel displays progress, the
last successful sync, counts, and failures. Automatic sync begins when a configured worker
next runs. No connection is attempted when URL/token are absent.

## Ownership and missing inventory

- NetBox owns the imported name and coordinates. Local edits to these fields are disabled;
  the asset update API preserves them for NetBox imports.
- OSINT Watch owns radius, minimum severity, monitored categories, and associated domains/IPs.
  A sync never overwrites these rules. New imports use the usual 25-km/moderate defaults.
- Identity is the NetBox endpoint plus site ID, not the name. Repeated sync and renames do not
  duplicate assets. Manual assets are never merged or changed by the integration.
- New sites without valid coordinates are skipped and counted. Previously imported sites
  without valid coordinates are marked `unlocated`; missing sites are marked `missing`.
  Their last known geometry is retained for inspection, but they are hidden from the map and
  excluded from exposure. Related alerts resolve. Returning sites resume monitoring.
- Changing the configured NetBox instance marks old-instance imports missing after the next
  successful snapshot. No saved asset is automatically deleted. A locally deleted import
  returns on the next sync if its site is still visible in NetBox.
- A failed or incomplete sync changes no assets. Previous locations remain available, and
  the failure/last-success timestamps explicitly indicate that the inventory may be stale.
  Changes in NetBox permissions can look like missing inventory; review that before deleting.

Pagination is bounded to 100 pages/10,000 sites, 16 MB per page, and a five-minute fetch
budget. All pages must succeed and match the advertised count before publication. Redirects
and next-page URLs outside the exact configured endpoint are rejected before sending the
secret. NetBox does not provide a transactional snapshot across paginated requests; duplicate
IDs/count changes fail the run and are retried. The job queue deduplicates pending requests
and uses the existing bounded retry policy.

## API

- `GET /api/v1/integrations/netbox`: read scope; configuration presence, schedule, latest job,
  last attempt/success, result counts and sanitized error. No URL credential/token is returned.
- `POST /api/v1/integrations/netbox/sync`: admin scope; returns HTTP 202 and `{id: job_uuid}`.
- `GET /api/v1/assets`: includes external_source, external_instance, external_id, sync_state,
  and last_synced_at. Existing manual assets have null import metadata.

References: [NetBox sites](https://netboxlabs.com/docs/netbox/v4.4/models/dcim/site/),
[NetBox REST authentication and pagination](https://netbox.readthedocs.io/en/stable/integrations/rest-api/).

Verification uses a mock NetBox transport and real PostGIS. A real NetBox instance/token was
not provided, so production connectivity and your instance's permissions require a first sync.
