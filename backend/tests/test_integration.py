from datetime import timedelta

from osint_watch.db import connection
from osint_watch.models import Category, now
from osint_watch.store import maintenance, refresh_exposure, upsert_event


def insert(event):
    with connection() as conn:
        upsert_event(conn, event)
        return str(
            conn.execute(
                "SELECT id FROM events WHERE external_id=%s", (event.external_id,)
            ).fetchone()["id"]
        )


def test_revision_idempotency_and_export(client, event):
    identifier = insert(event)
    with connection() as conn:
        assert not upsert_event(conn, event)
        assert conn.execute("SELECT count(*) AS n FROM changes").fetchone()["n"] == 1
    response = client.get("/api/v1/events").json()
    assert response["features"][0]["id"] == identifier
    event.title = "Revised earthquake"
    event.updated_at = now()
    insert(event)
    revisions = client.get("/api/v1/events/" + identifier).json()["revisions"]
    assert len(revisions) == 2
    changes = client.get("/api/v1/events/changes").json()
    assert [r["cursor"] for r in changes["changes"]] == [1, 2]


def test_spatial_alert_lifecycle(client, event):
    insert(event)
    asset = client.post(
        "/api/v1/assets",
        json={
            "name": "Office",
            "geometry": {"type": "Point", "coordinates": [-105, 40]},
            "radius_km": 10,
        },
    ).json()
    alerts = client.get("/api/v1/alerts").json()["items"]
    assert len(alerts) == 1 and "intersects Office" in alerts[0]["reason"]
    assert client.post("/api/v1/alerts/" + alerts[0]["id"] + "/acknowledge").status_code == 200
    with connection() as conn:
        refresh_exposure(conn)
    assert client.get("/api/v1/alerts").json()["items"][0]["status"] == "acknowledged"
    event.status = "cancelled"
    event.updated_at = now()
    insert(event)
    with connection() as conn:
        refresh_exposure(conn)
    assert client.get("/api/v1/alerts").json()["items"][0]["status"] == "resolved"
    assert client.delete("/api/v1/assets/" + asset["id"]).status_code == 200


def test_hotspot_and_perimeter_thresholds(client, event):
    client.post(
        "/api/v1/assets",
        json={
            "name": "Site",
            "geometry": {"type": "Point", "coordinates": [-105, 40]},
            "min_severity": 2,
        },
    )
    event.source_id = "firms"
    event.external_id = "hotspot"
    event.category = Category.HOTSPOT
    event.severity = 1
    insert(event)
    event.source_id = "nifc"
    event.external_id = "perimeter"
    event.category = Category.WILDFIRE
    event.severity = 2
    insert(event)
    with connection() as conn:
        refresh_exposure(conn)
    alerts = client.get("/api/v1/alerts").json()["items"]
    assert len(alerts) == 1 and alerts[0]["category"] == "wildfire_perimeter"
    with connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM event_links").fetchone()["n"] == 0


def test_geo_filters_and_tiles(client, event):
    insert(event)
    assert len(client.get("/api/v1/events?bbox=-106,39,-104,41").json()["features"]) == 1
    assert len(client.get("/api/v1/events?lon=-70&lat=40&radius_km=1").json()["features"]) == 0
    assert client.get("/api/v1/events?bbox=broken").status_code == 422
    assert client.get("/api/v1/events?since=2026-01-01T00:00:00").status_code == 422
    tile = client.get("/api/v1/tiles/0/0/0.pbf")
    assert tile.status_code == 200 and len(tile.content) > 0
    assert client.get("/api/v1/tiles/0/2/0.pbf").status_code == 422


def test_source_permission_all_surfaces(client, event):
    identifier = insert(event)
    with connection() as conn:
        conn.execute("UPDATE sources SET export_allowed=false WHERE id='usgs'")
    assert client.get("/api/v1/events").json()["features"] == []
    assert client.get("/api/v1/events/" + identifier).status_code == 404
    assert client.get("/api/v1/events/changes").json()["changes"] == []
    assert client.get("/api/v1/dashboard").json()["active_events"] == 0
    assert len(client.get("/api/v1/tiles/0/0/0.pbf").content) == 0
    with connection() as conn:
        assert conn.execute("SELECT count(*) AS n FROM export_events").fetchone()["n"] == 0


def test_api_token_permissions_and_revocation(client, event):
    result = client.post("/api/v1/tokens", json={"name": "GIS", "scopes": ["read"]}).json()
    admin = client.headers["Authorization"]
    client.headers["Authorization"] = "Bearer " + result["token"]
    assert client.get("/api/v1/events").status_code == 200
    assert (
        client.post(
            "/api/v1/assets",
            json={"name": "x", "geometry": {"type": "Point", "coordinates": [0, 0]}},
        ).status_code
        == 403
    )
    assert client.get("/api/v1/tokens").status_code == 403
    client.headers["Authorization"] = admin
    client.delete("/api/v1/tokens/" + result["id"])
    client.headers["Authorization"] = "Bearer " + result["token"]
    assert client.get("/api/v1/events").status_code == 401


def test_import_atomicity(client):
    response = client.post(
        "/api/v1/assets/import",
        json={"format": "csv", "content": "name,longitude,latitude\nValid,-105,40\nInvalid,999,40"},
    )
    assert response.status_code == 422
    assert client.get("/api/v1/assets").json()["total"] == 0
    assert (
        client.post(
            "/api/v1/assets/import",
            json={"format": "csv", "content": "name,longitude,latitude\nOffice,-105,40"},
        ).json()["created"]
        == 1
    )


def test_tombstones_and_expired_cursor(client, event):
    event.updated_at = now() - timedelta(days=100)
    event.occurred_at = event.updated_at
    event.expires_at = now() - timedelta(days=99)
    insert(event)
    with connection() as conn:
        maintenance(conn, 7, 90)
    changes = client.get("/api/v1/events/changes").json()["changes"]
    assert changes[-1]["operation"] == "delete"
    with connection() as conn:
        conn.execute("UPDATE changes SET created_at=now()-interval '100 days'")
        maintenance(conn, 7, 90)
    assert client.get("/api/v1/events/changes?cursor=0").status_code == 410


def test_source_staleness(client):
    with connection() as conn:
        conn.execute("UPDATE sources SET last_success=now()-interval '2 days' WHERE id='usgs'")
    source = next(s for s in client.get("/api/v1/sources").json()["items"] if s["id"] == "usgs")
    assert source["health"] == "stale"


def test_login_csrf_and_optional_services(client):
    del client.headers["Authorization"]
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "test-admin-password-123"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/events").status_code == 200
    assert client.post("/api/v1/tokens", json={"name": "test"}).status_code == 403
    client.headers["Origin"] = "http://localhost:8080"
    assert (
        client.post(
            "/api/v1/summaries", json={"event_ids": ["00000000-0000-0000-0000-000000000000"]}
        ).status_code
        == 409
    )
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/events").status_code == 401


def test_pagination(client, event):
    for i in range(3):
        event.external_id = str(i)
        insert(event)
    a = client.get("/api/v1/events?limit=2").json()
    b = client.get("/api/v1/events", params={"limit": 2, "cursor": a["next_cursor"]}).json()
    assert len(a["features"]) == 2 and len(b["features"]) == 1
    assert not {f["id"] for f in a["features"]} & {f["id"] for f in b["features"]}


def test_webhook_signature_retry_and_export_recheck(client, event, monkeypatch):
    import hashlib
    import hmac

    import httpx

    from osint_watch import worker
    from osint_watch.config import settings
    from osint_watch.store import enqueue

    insert(event)
    client.post(
        "/api/v1/assets",
        json={"name": "Hook site", "geometry": {"type": "Point", "coordinates": [-105, 40]}},
    )
    with connection() as conn:
        hook = conn.execute(
            "INSERT INTO webhooks(name,url,secret) VALUES ('test','https://example.com/hook','signing-secret') RETURNING id"
        ).fetchone()["id"]
        alert = conn.execute("SELECT id FROM alerts").fetchone()["id"]
        conn.execute("UPDATE sources SET enabled=false")
        job_id = enqueue(conn, "webhook", {"webhook_id": str(hook), "alert_id": str(alert)})
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 200)

    real_client = httpx.Client
    monkeypatch.setattr(
        worker.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler))
    )
    monkeypatch.setattr(worker, "validate_url", lambda *args: None)
    monkeypatch.setattr(settings(), "job_kinds", "webhook")
    worker.tick()
    with connection() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=%s", (job_id,)).fetchone()
        assert job["status"] == "pending" and job["attempts"] == 1
        conn.execute("UPDATE jobs SET available_at=now() WHERE id=%s", (job_id,))
    worker.tick()
    with connection() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=%s", (job_id,)).fetchone()
        assert job["status"] == "complete" and job["attempts"] == 2
        conn.execute("UPDATE sources SET export_allowed=false WHERE id='usgs'")
    assert worker.deliver_webhook(job).get("skipped")
    assert len(calls) == 2
    stamp = calls[1].headers["X-Watch-Timestamp"]
    expected = hmac.new(
        b"signing-secret", stamp.encode() + b"." + calls[1].content, hashlib.sha256
    ).hexdigest()
    assert calls[1].headers["X-Watch-Signature"] == "sha256=" + expected
    assert calls[0].headers["X-Watch-Delivery"] == calls[1].headers["X-Watch-Delivery"]


def test_ai_rejects_invented_evidence(client, event, monkeypatch):
    import json

    import httpx

    from osint_watch import worker
    from osint_watch.config import settings

    identifier = insert(event)
    monkeypatch.setattr(settings(), "ollama_url", "http://ollama:11434")
    result = {"summary": "Reported earthquake", "evidence_ids": ["invented"]}
    real_client = httpx.Client
    monkeypatch.setattr(
        worker.httpx,
        "Client",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"response": json.dumps(result)})
            )
        ),
    )
    import pytest

    with pytest.raises(ValueError, match="evidence references"):
        worker.summarize({"event_ids": [identifier]})
    result["evidence_ids"] = [identifier]
    assert worker.summarize({"event_ids": [identifier]})["evidence_ids"] == [identifier]


def test_malformed_cursor_and_cross_source_link(client, event):
    import base64

    identifier = insert(event)
    assert (
        client.get("/api/v1/events?cursor=" + base64.urlsafe_b64encode(b"{}").decode()).status_code
        == 422
    )
    event.source_id = "gdacs"
    event.external_id = "other-evidence"
    insert(event)
    related = client.get("/api/v1/events/" + identifier).json()["related"]
    assert len(related) == 1


def test_webhook_lifecycle_is_idempotent(client, event):
    with connection() as conn:
        conn.execute(
            "INSERT INTO webhooks(name,url,secret) VALUES ('lifecycle','https://example.com','test')"
        )
    insert(event)
    client.post(
        "/api/v1/assets",
        json={"name": "Lifecycle", "geometry": {"type": "Point", "coordinates": [-105, 40]}},
    )
    with connection() as conn:
        refresh_exposure(conn)
        assert (
            conn.execute("SELECT count(*) AS n FROM jobs WHERE kind='webhook'").fetchone()["n"] == 1
        )
    alert = client.get("/api/v1/alerts").json()["items"][0]
    assert client.post("/api/v1/alerts/" + alert["id"] + "/acknowledge").status_code == 200
    event.status = "cancelled"
    event.updated_at = now()
    insert(event)
    with connection() as conn:
        refresh_exposure(conn)
        assert (
            conn.execute("SELECT count(*) AS n FROM jobs WHERE kind='webhook'").fetchone()["n"] == 3
        )


def test_gis_database_role_has_only_export_access(client):
    import psycopg
    import pytest

    with connection() as conn:
        conn.execute("SET LOCAL ROLE watch_gis")
        assert conn.execute("SELECT count(*) FROM export_events").fetchone()
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT * FROM credentials")
