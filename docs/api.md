# API and GIS integration

All application routes are under `/api/v1`. `/api/openapi.json` is the machine-readable
contract; `/api/docs` is the interactive reference. The UI uses the same API.

## Authentication

Use `Authorization: Bearer $WATCH_API_TOKEN` for integrations. Create tokens in Settings.
`read` permits events, GIS, assets, exposure, sources and dashboard. `write` adds asset CRUD
and alert acknowledgment; issue `read,write` together. `admin` permits all operations,
including credentials, source management, analysis jobs and webhook subscriptions.
Tokens expire (default 90 days) and can be revoked. Token digests, not bearer strings,
are stored. Browser sessions use HttpOnly SameSite=Strict cookies, 12-hour expiry, and
an Origin check for mutation requests. Set WATCH_PUBLIC_URL to the exact browser origin.

## Event queries

```sh
curl -H "Authorization: Bearer $WATCH_API_TOKEN" \
  'http://localhost:8080/api/v1/events?bbox=-106,39,-104,41&limit=100'
```

Parameters: `bbox=west,south,east,north`, `lon`, `lat`, `radius_km`, `since`, `until`,
`category` (comma-separated), `source` (comma-separated), `active`, `limit`, `cursor`.
Times require explicit UTC offsets. Coordinates are WGS84 longitude/latitude.
Split antimeridian-crossing bounding boxes into two queries.
The time filter applies to source update time; event occurrence time is retained separately.

Responses are GeoJSON FeatureCollections with `features` and `next_cursor`. Features have
stable UUID IDs and source-specific external IDs in properties. Null geometry means the
source record is unlocated; never place it at a guessed centroid.
Severity: 0 unknown, 1 low, 2 moderate, 3 high, 4 extreme. This is category-specific
triage, not a calibrated universal risk probability. Original source severity is preserved.

`GET /events/{id}` includes evidence, recent revisions, candidate duplicate links, and exposure.
`GET /tiles/{z}/{x}/{y}.pbf` serves layer `events`, with category/source/since/until filters.
Tiles require the same credentials. `GET /dashboard` accepts category/source/since filters.

## Incremental synchronization

1. Capture `/events/sync-state`'s cursor **before** starting the full snapshot.
2. Page `/events?active=false` and upsert all features by UUID.
3. Read `/events/changes?cursor=...` from the captured cursor. Apply upserts and deletion
   tombstones, advancing to `next_cursor` even when the returned changes list is empty.
4. Continue while `has_more` is true, then poll periodically. Duplicate delivery is harmless.

Changes are retained 90 days by default. HTTP 410 means the cursor expired; rebuild the
snapshot. Source-restricted records are filtered at read time. If an administrator changes
source export policy directly in configuration/storage, consumers must rebuild their snapshot
to remove previously downloaded records; already exported data cannot be recalled.

## Assets and alerts

`POST /assets` and `PUT /assets/{id}` accept:

```json
{"name":"Denver office","geometry":{"type":"Point","coordinates":[-104.99,39.74]},"radius_km":25,"min_severity":2,"categories":["wildfire_perimeter","fire_weather","earthquake"],"domains":[]}
```

Areas use Polygon or MultiPolygon geometry. `/assets/import` accepts `{format: "csv" |
"geojson", content: "..."}` with up to 1,000 records, validated atomically. CSV columns:
name, longitude, latitude, optional radius_km/min_severity.

`GET /alerts` and `/exposure` support status, filters, limit and offset.
`POST /alerts/{id}/acknowledge` records operator acknowledgment; the worker resolves alerts
when an event expires, is cancelled, or no longer meets the asset rule.

## Webhooks

`POST /webhooks` accepts name and URL, returning a signing secret once. Deliveries are
queued on creation, acknowledgment, resolution, or changed exposure and retried up to five attempts with exponential delay. Consumers deduplicate
by `X-Watch-Delivery`. Verify `X-Watch-Signature` as HMAC-SHA256 over:
`X-Watch-Timestamp + "." + exact_body_bytes`. Reject timestamps older than five minutes.
Each delivery reports current alert state; consumers can fetch its event_id for full evidence.
Use constant-time comparison. `/jobs` exposes delivery status without returning secrets.
Redirects are not followed. Private destinations require WATCH_ALLOWED_OUTBOUND_HOSTS.

## OGC API Features

Use `/gis/collections/events/items?f=json` with your Bearer token. Bbox, datetime and
standard collection discovery are handled by pygeoapi. The database view excludes
export-restricted sources; the reverse proxy authenticates every GIS request. Internal
container ports must not be exposed directly. A separate read-only database role can select only
the export view and required spatial metadata; it cannot read credentials or raw evidence. This release does not implement WMS or Esri
FeatureServer emulation.

## Python example

```python
import os
import httpx

with httpx.Client(base_url="http://localhost:8080/api/v1",
                  headers={"Authorization": f"Bearer {os.environ['WATCH_API_TOKEN']}"}) as client:
    params = {"bbox": "-106,39,-104,41", "limit": 100}
    while True:
        response = client.get("/events", params=params)
        response.raise_for_status()
        page = response.json()
        for feature in page["features"]:
            integrate_feature(feature)  # Your company's GIS adapter
        if not page["next_cursor"]:
            break
        params["cursor"] = page["next_cursor"]
```

Errors use `{error: {code, message, fields?}}`; 401 missing/expired credentials, 403
insufficient scope/origin mismatch, 409 configuration conflict, 410 expired sync cursor,
422 invalid input, 429 rate limit. Default rate limit is 300 requests/minute per token.
