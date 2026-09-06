# Public-source connectors

Built-in definitions live in `config/sources.yaml` and are seeded once. Operator pause
settings survive restarts. To change an existing definition, use a migration or an explicit
SQL update; editing YAML alone intentionally does not overwrite saved configuration.
All sources preserve stable external IDs, timestamps, evidence links, original severity,
confidence, and location precision. Configure a contact address in WATCH_USER_AGENT for NWS.

## Adding a feed

Sources → Add public source accepts a public HTTP(S) URL, attribution and adapter settings.
Export is off by default; enable only when the source permits redistribution. With export
off, records are collected but excluded from the map, API, GIS, exposure and outbound alerts.
No generic scraper or arbitrary Python execution is provided.

### GeoJSON

Requires FeatureCollection with stable feature IDs or an `id_field` property, and a source
timestamp. Adapter config may include:

```json
{"id_field":"incident_id","title_field":"name","time_field":"started","updated_field":"modified","severity_field":"priority","params":{"format":"geojson"}}
```

Generic priority must be 0–4. Fields status, expires_at, url, description, precision and
source_severity are recognized. Missing optional expiry defaults to seven days after occurrence.
Pagination follows `pagination.next` or a link with `rel=next`, capped at 100 pages with
loop detection. Responses are bounded at 32 MB after decompression.

### ArcGIS FeatureServer

Supply the **layer URL**, ending in `/FeatureServer/0`, not `/query`. The adapter queries
stable object IDs first, then batches 200 IDs per request with `outSR=4326` and `f=geojson`.
Config accepts a `where` clause plus generic field mappings. NIFC has its own normalization.
Transfer-limit/error responses fail the collection rather than silently truncate it.

### RSS/Atom

Published/updated time and a stable GUID or link are required. Source geotags are retained;
unlocated reports remain unlocated. Feed text is never rendered as HTML. RSS reports are
unrated and cannot trigger the default moderate-severity exposure threshold.

## Built-in semantics and limits

- USGS: seven-day feed, five-minute polling; original magnitude preserved. Epicenter distance
  is approximate exposure, not modeled shaking. Magnitude <3 low, 3–4.9 moderate, 5–6.9 high,
  ≥7 extreme; missing magnitude unknown. Seven-day active window.
- NWS: actual active alerts every five minutes; Red Flag/Fire Weather → fire_weather,
  flood/tsunami → flood, others → severe_weather. CAP cancellations/supersession retained.
  Expiry follows source timestamps. Official zones fill absent polygons only when all referenced zones resolve; raw source geometries are preserved.
- NIFC: wildfire (WF) perimeters updated in the past 14 days, every 30 minutes. Prescribed
  fires excluded. Perimeter severity defaults to moderate triage because a boundary does not
  supply an impact severity. Containment/out-of-date boundaries expire; source area retained.
  Stable polygon IDs preserve separate perimeter features for the same incident. Invalid polygons
  are quarantined in raw evidence, counted as rejected, and cause degraded source health.
- FIRMS: NOAA-20 VIIRS, US-region rectangle including Alaska/Hawaii, previous day, every
  30 minutes. Low-severity thermal anomalies; confidence is sensor confidence, not fire severity.
  A free NASA MAP_KEY is required. Satellite latency and cloud obscuration remain limitations.
- GDACS: recent global feed every 30 minutes. Native Green/Orange/Red severity retained.
  Point locations are context, not impact polygons. GDACS wildfire summaries use Other hazards,
  never the reported-perimeter layer. This connector ingests the recent-event response, not a full archive.
- GDELT: 15-minute export files, action-country US and CAMEO root codes 14/18/19/20. Initial
  two-hour catch-up; at most eight files per run and one-day recovery window. Longer downtime
  creates a documented coverage gap. Location precision is news-coded, not verified.
  Demonstrations default low; reported conflict moderate. Country/state-level geocodes remain
  unlocated for exposure; city-level centroids are explicitly approximate. Article links retain publisher attribution.
  Column positions follow the [GDELT 2.0 codebook](https://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf), including its additional ADM2 fields.

Failures retry with bounded exponential delay; source health shows last success, error and
rejected records. A feed with only invalid records fails. Schema changes require adapter updates.
This is broad public coverage, not a claim of complete real-time national emergency coverage.

Primary references: [USGS](https://earthquake.usgs.gov/earthquakes/feed/v1.0/geojson.php),
[NWS](https://www.weather.gov/documentation/services-web-api),
[NIFC](https://data-nifc.opendata.arcgis.com/),
[FIRMS](https://firms.modaps.eosdis.nasa.gov/api/area/),
[GDACS](https://www.gdacs.org/gdacsapi/swagger/index.html),
[GDELT](https://www.gdeltproject.org/data.html).
