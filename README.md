# OSINT Watch

A self-hosted map and physical-risk dashboard built around public hazard feeds.
Track earthquakes, reported wildfire perimeters, satellite hotspots, fire-weather and flood alerts,
and news-derived unrest around saved sites and areas. Every event retains its source and uncertainty.

## Start

Requires Docker with Compose, roughly 4 cores / 8 GB RAM and 100 GB SSD. PostGIS currently
uses the amd64 image; ARM hosts run it under emulation.

```sh
python3 scripts/setup.py
docker compose up -d --build
```

Open [OSINT Watch](http://localhost:8080). Sign in as `admin` using `WATCH_ADMIN_PASSWORD` in the generated
`.env` file. The setup script creates unique credentials and never prints them. Never commit `.env`.
First collection takes several minutes; empty or stale feeds are shown honestly.

For LAN access, set `WATCH_BIND=0.0.0.0` and `WATCH_PUBLIC_URL` to the actual browser origin.
For remote access, terminate HTTPS at your reverse proxy, set `WATCH_SECURE_COOKIES=true`,
and keep PostGIS, the API, GIS server, and optional tool services on the private Compose network.

## Public data

- **USGS:** earthquakes (global baseline).
- **NWS:** US weather, flood, and fire-weather alerts; resolves official alert zones when possible.
- **NIFC/WFIGS:** US wildfire perimeters updated within the last 14 days.
- **NASA FIRMS:** NOAA-20 VIIRS detections in a US-region bounding box; add a free
  [NASA map key](https://firms.modaps.eosdis.nasa.gov/api/map_key/) as `WATCH_FIRMS_KEY`.
- **GDACS:** recent global multi-hazard context.
- **GDELT:** incremental US-location demonstration/conflict signals from news coding.

Hotspots are thermal detections, not confirmed fires. Fire-weather alerts are conditions,
not fire incidents. Peaceful demonstrations receive low severity by default. News coding is
unverified. Missing geometry is retained in the event list but never used to fabricate exposure.

Add additional public GeoJSON, ArcGIS FeatureServer, or RSS/Atom feeds from **Sources**.
See [connector configuration](docs/connectors.md) for field mappings and collection limits.

## NetBox assets

Sync NetBox sites into saved assets, on demand or hourly, while retaining local exposure rules.
Configure the NetBox base URL and read-only token in `.env`, then use **Saved assets → Sync from NetBox**.
See [NetBox setup and sync behavior](docs/netbox.md).

## Mapping integrations

Create a read token in **Settings → API access**. Use it as `Authorization: Bearer …`.

- REST/OpenAPI: `/api/docs`, `/api/openapi.json`
- GeoJSON: `/api/v1/events?bbox=-106,39,-104,41`
- Vector tiles: `/api/v1/tiles/{z}/{x}/{y}.pbf`, layer `events`
- OGC API Features: `/gis/collections/events/items?f=json`
- Incremental sync: `/api/v1/events/sync-state` and `/api/v1/events/changes`
- Assets, exposure, alerts, sources, jobs, tokens, webhooks: `/api/v1/...`

The UI uses these same endpoints. [API guide and Python example](docs/api.md).

## Optional local intelligence

For an existing Ollama server, set `WATCH_OLLAMA_URL` to its local/LAN URL and restart
`api` and `enrichment-worker`. Model defaults to `qwen2.5:3b`; install it on that server.

For the bundled service:

```sh
# Set WATCH_OLLAMA_URL=http://ollama:11434 in .env first.
docker compose --profile ai up -d
docker compose exec ollama ollama pull qwen2.5:3b
```

AI summarizes supplied evidence and validates returned citation IDs. It does not establish truth,
change severity, or trigger scans. A separate worker keeps inference off the collection queue.
Model downloads and inference require additional storage/RAM; 8 GB is the core platform target.

For SpiderFoot, set `WATCH_SPIDERFOOT_URL=http://spiderfoot:8001`, retain the generated shared
bridge token, and run `docker compose --profile spiderfoot up -d --build`. Attach a domain/IP to
an asset and request **Passive enrichment**. Results appear in **Settings → Jobs**. The bridge
uses pinned upstream v4.0 with `-u passive`; it accepts no arbitrary modules or shell commands.

## Operations and development

- [Architecture, security, and data semantics](docs/architecture.md)
- [Backup, restore, retention, and health](docs/operations.md)
- [Development and test commands](docs/development.md)
- [Executed checks, benchmarks, and known limits](docs/verification.md)

This is a situational-awareness tool; source coverage and update latency vary. Source evidence,
uncertainty, and feed health should inform every interpretation.

### Frontend appearance
Use **Appearance** in the page header (or sign-in screen) to choose **Light theme**,
**Dark theme**, or **System theme**. The choice is saved in this browser; System follows
your operating system. The default basemap has a matching dark style. A custom basemap
keeps the style configured by your administrator.
