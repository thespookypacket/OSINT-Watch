import pytest

from osint_watch.connectors.base import Batch, timestamp
from osint_watch.connectors.feeds import (
    add_feature,
    fetch_arcgis,
    fetch_firms,
    fetch_geojson,
    fetch_rss,
    normalize,
    weather_category,
)
from osint_watch.models import AssetIn, Category


@pytest.mark.parametrize(
    "name,category",
    [
        ("Red Flag Warning", Category.FIRE_WEATHER),
        ("Fire Weather Watch", Category.FIRE_WEATHER),
        ("Flash Flood Warning", Category.FLOOD),
        ("Tornado Warning", Category.WEATHER),
    ],
)
def test_weather_categories(name, category):
    assert weather_category(name) == category


def test_invalid_geometry():
    with pytest.raises(ValueError):
        AssetIn(name="bad", geometry={"type": "Point", "coordinates": [200, 0]})
    with pytest.raises(ValueError):
        AssetIn(
            name="crossed",
            geometry={"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [1, 0], [0, 1], [0, 0]]]},
        )


def test_usgs_and_unknown_magnitude():
    record = {
        "id": "a",
        "geometry": {"type": "Point", "coordinates": [-105, 40, 5]},
        "properties": {
            "mag": None,
            "time": 1700000000000,
            "updated": 1700000000000,
            "title": "Earthquake",
        },
    }
    event = normalize({"id": "usgs"}, record)
    assert event.severity == 0 and event.geometry["coordinates"][2] == 5
    assert event.updated_at.tzinfo is not None


def test_perimeter_not_hotspot():
    record = {
        "id": 1,
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[-105, 40], [-104, 40], [-104, 41], [-105, 40]]],
        },
        "properties": {
            "poly_IRWINID": "stable",
            "poly_IncidentName": "Fire",
            "poly_CreateDate": 1700000000000,
            "poly_DateCurrent": 1700000000000,
        },
    }
    event = normalize({"id": "nifc"}, record)
    assert event.category == Category.WILDFIRE and event.external_id == "1"
    assert "severity not supplied" in event.source_severity


def test_cancellation():
    event = normalize(
        {"id": "nws"},
        {
            "id": "cap",
            "geometry": None,
            "properties": {
                "event": "Red Flag Warning",
                "sent": "2026-09-01T00:00:00Z",
                "messageType": "Cancel",
                "severity": "Severe",
            },
        },
    )
    assert event.status == "cancelled" and event.category == Category.FIRE_WEATHER


def test_bad_record_quarantine():
    batch = Batch()
    add_feature(batch, {"id": "usgs"}, {"properties": {}})
    assert batch.rejected == 1 and not batch.events


class Reply:
    def __init__(self, data=None, text=""):
        self.data = data
        self.text = text

    def json(self):
        return self.data


class FakeFetch:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        return next(self.replies)


def test_arcgis_stable_id_pagination():
    source = {
        "id": "custom",
        "name": "Public data",
        "category": "other_hazard",
        "url": "https://example.com/0",
        "config": {},
    }
    fetcher = FakeFetch(
        [Reply({"objectIds": list(range(201))}), Reply({"features": []}), Reply({"features": []})]
    )
    batch = fetch_arcgis(source, fetcher)
    assert len(fetcher.calls) == 3 and batch.checkpoint["object_count"] == 201
    assert len(fetcher.calls[1][1]["objectIds"].split(",")) == 200


def test_geojson_pagination_and_loop():
    fetcher = FakeFetch(
        [
            Reply(
                {
                    "type": "FeatureCollection",
                    "features": [],
                    "pagination": {"next": "https://example.com/b"},
                }
            ),
            Reply({"type": "FeatureCollection", "features": []}),
        ]
    )
    assert (
        fetch_geojson({"id": "generic", "url": "https://example.com/a"}, fetcher).checkpoint[
            "pages"
        ]
        == 2
    )
    fetcher = FakeFetch(
        [
            Reply(
                {
                    "type": "FeatureCollection",
                    "features": [],
                    "pagination": {"next": "https://example.com/a"},
                }
            )
        ]
    )
    with pytest.raises(ValueError, match="pagination"):
        fetch_geojson({"id": "generic", "url": "https://example.com/a"}, fetcher)


def test_firms_sensor_semantics(monkeypatch):
    from osint_watch.config import settings

    monkeypatch.setattr(settings(), "firms_key", "test-key")
    fetcher = FakeFetch(
        [
            Reply(
                text="latitude,longitude,acq_date,acq_time,confidence,frp\n40,-105,2026-09-01,0200,h,5\n"
            )
        ]
    )
    event = fetch_firms({"id": "firms"}, fetcher).events[0]
    assert (
        event.category == Category.HOTSPOT and event.severity == 1 and event.confidence == "sensor"
    )
    assert "not a fire boundary" in event.precision


def test_rss_unlocated_and_plain_text():
    feed = '<rss version="2.0"><channel><title>Alerts</title><item><title>Reported event</title><link>https://example.com/a</link><pubDate>Tue, 01 Sep 2026 00:00:00 GMT</pubDate></item></channel></rss>'
    event = fetch_rss(
        {
            "id": "rss",
            "name": "Public",
            "category": "reported_unrest",
            "url": "https://example.com",
        },
        FakeFetch([Reply(text=feed)]),
    ).events[0]
    assert event.geometry is None and event.severity == 0 and event.confidence == "reported"


def test_timestamp_units():
    assert timestamp(1700000000000) == timestamp(1700000000)
    with pytest.raises(ValueError):
        timestamp(None)


def test_compressed_http_response(monkeypatch):
    import gzip

    import httpx

    from osint_watch.connectors import base

    monkeypatch.setattr(base, "validate_url", lambda url, allowed="": url)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200, content=gzip.compress(b'{"features":[]}'), headers={"content-encoding": "gzip"}
        )
    )
    fetcher = base.Fetcher(transport)
    assert fetcher.get("https://example.com").json() == {"features": []}
    fetcher.close()


def test_nws_zone_resolution_preserves_raw_and_missing_coverage():
    page = {
        "type": "FeatureCollection",
        "features": [
            {
                "id": "warning",
                "geometry": None,
                "properties": {
                    "event": "Red Flag Warning",
                    "sent": "2026-09-01T00:00:00Z",
                    "affectedZones": ["https://example.com/a", "https://example.com/b"],
                },
            }
        ],
    }
    polygon = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
    batch = fetch_geojson(
        {"id": "nws", "url": "https://example.com"},
        FakeFetch([Reply(page), Reply({"geometry": polygon}), Reply({"geometry": None})]),
    )
    assert batch.events[0].geometry is None
    assert batch.raw[0]["features"][0]["geometry"] is None
    batch = fetch_geojson(
        {"id": "nws", "url": "https://example.com"},
        FakeFetch([Reply(page), Reply({"geometry": polygon}), Reply({"geometry": polygon})]),
    )
    assert batch.events[0].geometry["type"] == "Polygon"
    assert batch.events[0].precision == "official zone polygons"
    assert batch.raw[0]["features"][0]["geometry"] is None


def test_gdacs_fire_summary_is_not_perimeter():
    e = normalize(
        {"id": "gdacs"},
        {
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {"eventtype": "WF", "eventid": 1, "fromdate": "2026-09-01T00:00:00Z"},
        },
    )
    assert e.category == Category.OTHER
    assert "not an impact boundary" in e.precision


def test_gdelt_v2_country_location_precision_and_peaceful_signal():
    import io
    import zipfile

    from osint_watch.connectors.feeds import fetch_gdelt

    class BinaryReply(Reply):
        pass

    row = [""] * 61
    # Official v2 schema: ADM2 fields shift ActionGeo past the old v1 columns.
    row[0] = "123"
    row[1] = "20260906"
    row[26] = "141"
    row[28] = "14"
    row[31] = "9"
    row[51] = "3"
    row[52] = "Denver, Colorado"
    row[53] = "US"
    row[56] = "39.74"
    row[57] = "-104.99"
    row[59] = "20260906061500"
    row[60] = "https://example.com/evidence"
    coarse = row.copy()
    coarse[0] = "124"
    coarse[51] = "2"
    foreign = row.copy()
    foreign[0] = "125"
    foreign[53] = "CA"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("events.csv", "\n".join("\t".join(r) for r in [row, coarse, foreign]))
    reply = BinaryReply()
    reply.content = buf.getvalue()
    url = "https://data.gdeltproject.org/gdeltv2/20260906061500.export.CSV.zip"
    source = {"id": "gdelt", "checkpoint": {"last_file": url.replace("061500", "060000")}}
    batch = fetch_gdelt(source, FakeFetch([Reply(text="1 checksum " + url), reply]))
    assert len(batch.events) == 2
    assert batch.events[0].geometry["coordinates"] == [-104.99, 39.74]
    assert batch.events[0].category == Category.UNREST and batch.events[0].severity == 1
    assert batch.events[1].geometry is None
    assert batch.checkpoint["last_file"] == url
