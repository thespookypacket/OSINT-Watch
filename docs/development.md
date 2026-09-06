# Development and verification

Python 3.12+ and Node 22+. Create a venv and install `./backend[dev]`; run `npm ci` inside
frontend. Production uses Docker; the local test suite uses a separate PostGIS database.

```sh
python3 -m venv .venv
.venv/bin/pip install -c backend/constraints.txt -e './backend[dev]'
npm --prefix frontend ci
.venv/bin/ruff check backend
.venv/bin/mypy backend/osint_watch
npm --prefix frontend run lint
npm --prefix frontend run build
```

For integration tests expose PostGIS only on localhost:55432 using a local Compose override:

```yaml
services:
  db:
    ports: ['127.0.0.1:55432:5432']
```

Run `docker compose -f compose.yaml -f YOUR_OVERRIDE.yaml up -d db` then
`.venv/bin/pytest backend/tests -q`. Tests create `watch_test`, with per-test truncation limited
to that database. WATCH_TEST_DATABASE_URL can override the connection but its database name
must end in `_test`. Unit tests run without PostGIS; integration tests explicitly skip when
it is unavailable. Do not report skipped integration tests as passing.

The benchmark `.venv/bin/python scripts/benchmark.py` uses only `watch_benchmark_test` and
seeds 100,000 synthetic events and 1,000 assets. It measures actual query and tile generation
paths. These are server timings, not browser render latency or a guarantee on other hardware.

The browser workflow suite uses the running Compose deployment and creates disposable assets
with an `E2E` name prefix, cleaning them up using the API. No source or operator asset is removed.
Install the test browser with `cd frontend && npx playwright install chromium`, then run
`npm --prefix frontend run test:e2e` from the repository root. It reads the generated local admin credential without
printing it. Browser screenshots/reports go to a temporary directory, not the source tree.

See `docs/verification.md` for the checks actually performed during initial implementation.
