# Verification record — 2026-09-06

This is a working initial implementation, tested locally on macOS/Apple Silicon with Docker
Desktop and amd64 PostGIS emulation. The intended 4-core/8-GB homelab was not available;
measurements below are not a certification for that hardware.

## Automated checks

- Backend: 35 tests passed against a separate PostGIS test database; none skipped.
  Includes source parsing, ArcGIS/GeoJSON pagination, compressed HTTP responses, NWS zone
  completeness and cancellation, distinct fire-layer semantics, GDELT v2 US/city filtering,
  invalid geometry, duplicate/revised events, candidate evidence links, spatial exposure,
  acknowledgment/resolution, stale sources, scoped/revoked tokens, source export restrictions,
  sync cursors/tombstones, webhook signatures/retries/lifecycle, AI reference validation,
  read-only GIS database grants, and fixed passive SpiderFoot bridge policy.
- Frontend: 3 API/semantic unit tests passed. ESLint, TypeScript, Vite production build,
  backend Ruff and mypy passed.
- Browser: all 4 workflow tests passed. CSV failure/atomic import, create/edit/delete, map placement/overlay controls,
  evidence inspection, explainable polygon exposure, acknowledgment, source status, and
  390-pixel mobile layout passed. Area drawing/undo and GeoJSON import passed as well, in
  the workflow suite in `frontend/tests/workflows.spec.ts`.
- Premium UI audit: zero findings. DESIGN.md lint: zero errors/warnings.
- npm production dependency audit: zero reported vulnerabilities at verification time.

Python 3.14 local tests emit dependency deprecation warnings; production uses Python 3.12.
Vite warns about the separately lazy-loaded MapLibre bundle (~925 KB minified, ~250 KB gzip).
These warnings are retained, not hidden by disabling checks.

## Live deployment and data

Compose builds and starts API, PostGIS, collection worker, separate enrichment worker,
pygeoapi and web gateway. API/database/web/collection-worker health checks pass. Monitoring
operates with Ollama and SpiderFoot unconfigured.

Actual USGS, NWS, NIFC, GDACS and GDELT data was ingested. Corrected GDELT parsing replayed
108 US reported signals in the observed initial window. NASA FIRMS parsing is fixture-tested;
a real FIRMS request was not made because no NASA map key was provided.

The observed NIFC response contained 829 features: 766 valid perimeters and 63 invalid
geometries. Invalid records remain in raw evidence and source health reports degraded coverage.
No invalid polygon is silently repaired or treated as a trustworthy boundary.

Authenticated OGC requests returned GeoJSON with attribution; unauthenticated and revoked
credentials were denied, and writes were blocked. The GIS database role cannot read credentials.
Backup/restore was exercised twice into new databases without replacing the live workspace.
The final restoration contained 3,299 events, both migrations, and the GIS export grants.

SpiderFoot's optional image built successfully and its CLI help ran. The bridge's authorization
and fixed passive command are tested with a stub process. No real third-party scan was run.
Ollama reference validation was tested with mock responses; no real model was downloaded or
inference benchmarked.

## Performance

`scripts/benchmark.py` seeds only `watch_benchmark_test`, with 100,000 synthetic point events
and 1,000 fixed assets. Ten calls per read path:

| Path | Median | Maximum |
|---|---:|---:|
| Filtered event query | 74.09 ms | 87.83 ms |
| Vector tile generation | 160.11 ms | 195.38 ms |
| Dashboard query | 120.09 ms | 125.47 ms |

Full exposure recalculation: 1,787.39 ms. These measure Python query paths and PostGIS, excluding
HTTP authentication, network transit and browser rendering. Complex real wildfire polygons,
concurrent clients, cold caches and sustained multi-day ingestion can cost more. The requested
end-to-end two-second map target at 100,000 events still needs a benchmark on the target host.

## Operational limits

- External basemap/network access is required unless an operator supplies their own style URL.
- Retention defaults to raw 7 days and normalized/change history 90 days. Active long-lived
  hazards remain until inactive; source update windows and GDELT replay limits are documented.
- AI summaries are suggestions with checked citation IDs, not independently verified conclusions.
- Export policy changes require downstream snapshot resynchronization to purge previously
  downloaded data. No service can recall copies already exported to another system.
- Corporate SSO, multitenancy, moving assets, paid feeds, WMS, and offline basemap hosting remain
  deferred as specified in the plan.

## NetBox site sync (September 6, 2026)

- 44 backend tests passed against the isolated PostGIS test database, including authenticated
  pagination, cross-origin credential protection, duplicate imports, local-rule preservation,
  missing/unlocated sites, exposure resolution/reopening, failure retention and API permissions.
- 3 frontend unit tests and 5 browser workflows passed. NetBox browser coverage uses mocked
  status/queue responses for configured, pending, completed and failed requests; the unconfigured
  panel was also inspected in the in-app browser at a narrow viewport.
- Ruff, mypy, ESLint, TypeScript and production build passed. Strict UI audit reported no findings.
- Docker images rebuilt and migration 003 applied. The temporary database test port was removed.
- No real NetBox endpoint/token was supplied; real instance connectivity remains unverified.

## Dark mode (September 6, 2026)

- Added browser-local Light/Dark/System selection, startup preference application, live OS
  updates, cross-tab synchronization and graceful behavior when localStorage is unavailable.
- 3 frontend unit tests, 5 existing workflow tests and 2 theme browser tests passed. Theme
  coverage includes reload persistence, OS changes, cross-tab updates, blocked storage,
  overlay/opacity preservation, unsaved form preservation, native dialogs and 390px layout.
- Axe checks passed for the dark overview's text contrast, the asset dialog and Saved assets.
  Desktop/narrow screenshots and the running in-app browser were reviewed.
- ESLint, TypeScript, production build and strict UI audit passed. Rebuilt the Docker web
  service. The existing MapLibre bundle-size advisory remains unchanged.
- The default OpenFreeMap basemap uses its Dark style. Custom basemap styles remain unchanged.
