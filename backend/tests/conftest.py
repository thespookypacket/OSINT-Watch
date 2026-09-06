"""Integration tests use a separate database, never the operator workspace."""

import os
from pathlib import Path

import psycopg
import pytest
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from psycopg import sql

from osint_watch.config import settings

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def database():
    env = dotenv_values(ROOT / ".env")
    url = os.environ.get("WATCH_TEST_DATABASE_URL")
    if not url:
        password = env.get("POSTGRES_PASSWORD", "watch")
        url = f"postgresql://watch:{password}@127.0.0.1:55432/watch_test"
    parsed = psycopg.conninfo.conninfo_to_dict(url)
    if not parsed.get("dbname", "").endswith("_test"):
        raise RuntimeError("Test database must end in _test")
    admin = {**parsed, "dbname": "postgres"}
    try:
        with psycopg.connect(**admin, autocommit=True) as conn:
            if not conn.execute(
                "SELECT 1 FROM pg_database WHERE datname=%s", (parsed["dbname"],)
            ).fetchone():
                conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(parsed["dbname"])))
    except psycopg.OperationalError:
        pytest.skip("PostGIS unavailable; start the test database per docs/development.md")
    os.environ["WATCH_DATABASE_URL"] = url
    os.environ["WATCH_ADMIN_PASSWORD"] = "test-admin-password-123"
    os.environ["WATCH_SOURCE_CONFIG"] = str(ROOT / "config/sources.yaml")
    settings.cache_clear()
    from osint_watch.db import migrate

    migrate()
    yield url
    settings.cache_clear()


@pytest.fixture
def client(database):
    from osint_watch.api import app
    from osint_watch.db import connection
    from osint_watch.security import issue_token

    with connection() as conn:
        conn.execute(
            "TRUNCATE integration_sync,sources,events,changes,raw_payloads,event_links,assets,alerts,credentials,webhooks,jobs,users,rate_limits,audit_log,worker_health RESTART IDENTITY CASCADE"
        )
        conn.execute("UPDATE sync_state SET floor=0")
        conn.execute("INSERT INTO integration_sync(id) VALUES ('netbox')")
    with TestClient(app) as client:
        with connection() as conn:
            token = issue_token(conn, "test", ["admin"], 1)["token"]
        client.headers["Authorization"] = "Bearer " + token
        yield client


@pytest.fixture
def event():
    from datetime import timedelta

    from osint_watch.models import Category, EventIn, now

    return EventIn(
        source_id="usgs",
        external_id="test-quake",
        title="Test earthquake",
        category=Category.EARTHQUAKE,
        severity=3,
        source_severity="Magnitude 5.2",
        occurred_at=now(),
        updated_at=now(),
        expires_at=now() + timedelta(days=1),
        geometry={"type": "Point", "coordinates": [-105, 40]},
        confidence="official",
        evidence_url="https://earthquake.usgs.gov/",
    )
