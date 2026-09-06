"""Reproducible synthetic performance fixture in watch_benchmark_test only."""

import json
import os
import statistics
import time
from pathlib import Path

import psycopg
from dotenv import dotenv_values

root = Path(__file__).resolve().parent.parent
env = dotenv_values(root / ".env")
url = f"postgresql://watch:{env['POSTGRES_PASSWORD']}@127.0.0.1:55432/watch_benchmark_test"
params = psycopg.conninfo.conninfo_to_dict(url)
with psycopg.connect(**{**params, "dbname": "postgres"}, autocommit=True) as conn:
    if not conn.execute(
        "SELECT 1 FROM pg_database WHERE datname='watch_benchmark_test'"
    ).fetchone():
        conn.execute("CREATE DATABASE watch_benchmark_test")
os.environ["WATCH_DATABASE_URL"] = url
from osint_watch.config import settings

settings.cache_clear()
from osint_watch.db import connection, migrate

migrate()
with connection() as conn:
    conn.execute("TRUNCATE sources,events,assets RESTART IDENTITY CASCADE")
    conn.execute(
        "INSERT INTO sources(id,name,adapter,url,category,attribution,export_allowed) VALUES ('benchmark','Synthetic benchmark','geojson','https://example.com','earthquake','Synthetic test fixture',true)"
    )
    conn.execute("""INSERT INTO events(source_id,external_id,title,category,severity,source_severity,status,occurred_at,updated_at,expires_at,geom,precision,evidence_url,description,confidence,properties,fingerprint)
        SELECT 'benchmark',n::text,'Synthetic earthquake '||n,'earthquake',2,'Synthetic','active',now(),now(),now()+interval '1 day',
        ST_SetSRID(ST_MakePoint(-125+(n%1000)*.06,25+(n%583)*.04),4326),'synthetic','https://example.com','','unknown','{}',n::text FROM generate_series(1,100000) n""")
    conn.execute("""INSERT INTO assets(name,geom,radius_km,min_severity,categories)
        SELECT 'Synthetic asset '||n,ST_SetSRID(ST_MakePoint(-125+(n%1000)*.06,25+(n%583)*.04),4326),10,2,ARRAY['earthquake'] FROM generate_series(1,1000) n""")
    conn.execute("ANALYZE events")
    conn.execute("ANALYZE assets")
from osint_watch.routes_events import dashboard, list_events, tiles
from osint_watch.store import refresh_exposure

measurements = {}
for label, fn in [
    (
        "filtered_events",
        lambda: list_events(bbox="-106,39,-104,41", limit=100, radius_km=25),
    ),
    ("vector_tile", lambda: tiles(5, 6, 12)),
    ("dashboard", lambda: dashboard()),
]:
    samples = []
    for _ in range(10):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    measurements[label] = {
        "median_ms": round(statistics.median(samples), 2),
        "max_ms": round(max(samples), 2),
    }
start = time.perf_counter()
with connection() as conn:
    refresh_exposure(conn)
measurements["exposure_recompute_ms"] = round((time.perf_counter() - start) * 1000, 2)
print(json.dumps({"events": 100000, "assets": 1000, "timings": measurements}, indent=2))
