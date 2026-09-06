import httpx
import pytest

from osint_watch.config import settings
from osint_watch.db import connection
from osint_watch.netbox import fetch_sites, sync_sites


@pytest.fixture
def netbox_config(monkeypatch):
    monkeypatch.setattr(settings(), "netbox_url", "https://netbox.example/company")
    monkeypatch.setattr(settings(), "netbox_token", "secret-test-token")


def transport(sites):
    return httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"count": len(sites), "next": None, "results": sites}
        )
    )


def site(identifier=1, **values):
    return {"id": identifier, "name": "Office", "latitude": "40.0", "longitude": "-105.0", **values}


def test_pages_auth_and_coordinates(netbox_config, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Token secret-test-token"
        return httpx.Response(
            200,
            json={
                "count": 2,
                "next": "?offset=1" if len(calls) == 1 else None,
                "results": [site(len(calls))],
            },
        )

    assert len(fetch_sites(httpx.MockTransport(handler))) == 2
    assert calls[1].url.path == "/company/api/dcim/sites/"
    monkeypatch.setattr(settings(), "netbox_token", "nbt_key.secret")

    def bearer(request):
        assert request.headers["Authorization"] == "Bearer nbt_key.secret"
        return httpx.Response(200, json={"count": 0, "next": None, "results": []})

    assert fetch_sites(httpx.MockTransport(bearer)) == []


@pytest.mark.parametrize(
    "next_url",
    [
        "https://attacker.example/steal",
        "http://netbox.example/company/api/dcim/sites/",
        "https://netbox.example/api/users/",
    ],
)
def test_pagination_does_not_leak_token(netbox_config, next_url):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"count": 1, "results": [site()], "next": next_url})

    with pytest.raises(ValueError, match="pagination left"):
        fetch_sites(httpx.MockTransport(handler))
    assert len(calls) == 1


def test_incomplete_and_duplicate_snapshot(netbox_config):
    with pytest.raises(ValueError, match="Incomplete"):
        fetch_sites(
            httpx.MockTransport(
                lambda r: httpx.Response(200, json={"count": 2, "results": [site()], "next": None})
            )
        )
    with pytest.raises(ValueError, match="duplicate"):
        fetch_sites(transport([site(), site()]))


def test_sync_preserves_rules_and_source_ownership(client, netbox_config):
    assert sync_sites(transport([site()]))["created"] == 1
    asset = client.get("/api/v1/assets").json()["items"][0]
    assert asset["geometry"]["coordinates"] == [-105, 40] and asset["sync_state"] == "current"
    response = client.put(
        "/api/v1/assets/" + asset["id"],
        json={
            **asset,
            "name": "Override",
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "radius_km": 72,
            "min_severity": 1,
            "domains": ["example.com"],
        },
    )
    assert response.status_code == 200
    result = sync_sites(transport([site(name="Renamed", longitude="-104")]))
    assert result["created"] == 0 and result["updated"] == 1
    after = client.get("/api/v1/assets").json()["items"][0]
    assert after["id"] == asset["id"] and after["name"] == "Renamed"
    assert (
        after["radius_km"] == 72
        and after["min_severity"] == 1
        and after["domains"] == ["example.com"]
    )
    assert after["geometry"]["coordinates"] == [-104, 40]


def test_missing_and_unlocated_pause_exposure(client, event, netbox_config):
    from osint_watch.store import upsert_event

    with connection() as conn:
        upsert_event(conn, event)
    sync_sites(transport([site()]))
    assert client.get("/api/v1/alerts").json()["items"][0]["status"] == "open"
    result = sync_sites(transport([site(latitude=None)]))
    assert result["unlocated"] == 1
    assert client.get("/api/v1/assets").json()["items"][0]["sync_state"] == "unlocated"
    assert client.get("/api/v1/alerts").json()["items"][0]["status"] == "resolved"
    assert sync_sites(transport([]))["missing"] == 1
    assert client.get("/api/v1/assets").json()["total"] == 1
    sync_sites(transport([site()]))
    assert client.get("/api/v1/alerts").json()["items"][0]["status"] == "open"


def test_failed_sync_keeps_snapshot_and_hides_credentials(client, netbox_config):
    sync_sites(transport([site()]))
    before = client.get("/api/v1/assets").json()
    with pytest.raises(httpx.HTTPStatusError):
        sync_sites(httpx.MockTransport(lambda r: httpx.Response(403)))
    assert client.get("/api/v1/assets").json() == before
    state = client.get("/api/v1/integrations/netbox")
    assert state.json()["last_error"] and "secret-test-token" not in state.text


def test_queue_permissions_and_deduplication(client, netbox_config):
    first = client.post("/api/v1/integrations/netbox/sync")
    assert first.status_code == 202
    assert first.json() == client.post("/api/v1/integrations/netbox/sync").json()
    token = client.post("/api/v1/tokens", json={"name": "read", "scopes": ["read"]}).json()["token"]
    client.headers["Authorization"] = "Bearer " + token
    assert client.get("/api/v1/integrations/netbox").status_code == 200
    assert client.post("/api/v1/integrations/netbox/sync").status_code == 403
