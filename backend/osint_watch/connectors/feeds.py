"""Normalization for authoritative hazards and explicitly unconfirmed news signals."""

import csv
import io
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

import feedparser  # type: ignore[import-untyped]
import httpx

from ..config import settings
from ..models import Category, EventIn, now
from .base import Batch, Fetcher, timestamp

SEVERITIES = {"Unknown": 0, "Minor": 1, "Moderate": 2, "Severe": 3, "Extreme": 4}


def weather_category(name: str) -> Category:
    if any(word in name.lower() for word in ("red flag", "fire weather")):
        return Category.FIRE_WEATHER
    if any(word in name.lower() for word in ("flood", "tsunami")):
        return Category.FLOOD
    return Category.WEATHER


def normalize(source: dict[str, Any], feature: dict[str, Any]) -> EventIn:
    p = feature.get("properties", {})
    sid = source["id"]
    geom = feature.get("geometry")
    if sid == "usgs":
        mag = p.get("mag")
        severity = (
            0 if mag is None else (4 if mag >= 7 else 3 if mag >= 5 else 2 if mag >= 3 else 1)
        )
        occurred = timestamp(p["time"])
        return EventIn(
            source_id=sid,
            external_id=str(feature["id"]),
            title=p.get("title") or "Earthquake",
            category=Category.EARTHQUAKE,
            severity=severity,
            source_severity=f"Magnitude {mag}",
            occurred_at=occurred,
            updated_at=timestamp(p["updated"]),
            expires_at=occurred + timedelta(days=7),
            geometry=geom,
            precision="epicenter; impact radius is approximate",
            evidence_url=p.get("url", ""),
            confidence="official",
            properties={"magnitude": mag, "alert": p.get("alert")},
        )
    if sid == "nws":
        occurred = timestamp(p.get("onset") or p.get("effective") or p.get("sent"))
        return EventIn(
            source_id=sid,
            external_id=str(feature.get("id") or p["id"]),
            title=p.get("headline") or p["event"],
            category=weather_category(p["event"]),
            severity=SEVERITIES.get(p.get("severity", "Unknown"), 0),
            source_severity=p.get("severity", "Unknown"),
            status="cancelled" if p.get("messageType") == "Cancel" else "active",
            occurred_at=occurred,
            updated_at=timestamp(p.get("sent"), occurred),
            expires_at=timestamp(p.get("ends") or p.get("expires"), occurred + timedelta(days=1)),
            geometry=geom,
            precision=(
                "official zone polygons" if p.get("zone_geometry_resolved") else "alert polygon"
            )
            if geom
            else "zone geometry unavailable",
            evidence_url=str(feature.get("id") or p.get("id", "")),
            description=p.get("description") or "",
            confidence="official",
            properties={
                "event": p["event"],
                "area": p.get("areaDesc"),
                "references": p.get("references", []),
                "affectedZones": p.get("affectedZones", []),
            },
        )
    if sid == "nifc":
        occurred = timestamp(p.get("attr_FireDiscoveryDateTime") or p.get("poly_CreateDate"))
        updated = timestamp(
            p.get("poly_DateCurrent") or p.get("poly_PolygonDateTime") or p.get("poly_CreateDate"),
            occurred,
        )
        contained = p.get("attr_PercentContained")
        return EventIn(
            source_id=sid,
            external_id=str(
                p.get("poly_GlobalID")
                or p.get("GlobalID")
                or feature.get("id")
                or p["poly_IRWINID"]
            ),
            title=p.get("poly_IncidentName") or "Reported wildfire perimeter",
            category=Category.WILDFIRE,
            severity=2,
            source_severity="Reported perimeter; severity not supplied",
            occurred_at=occurred,
            updated_at=updated,
            expires_at=updated + timedelta(days=14),
            status="expired" if p.get("attr_ContainmentDateTime") else "active",
            geometry=geom,
            precision="reported perimeter; may lag actual fire spread",
            evidence_url="https://data-nifc.opendata.arcgis.com/",
            confidence="official",
            properties={
                "acres": p.get("poly_GISAcres"),
                "percent_contained": contained,
                "incident_id": p.get("poly_IRWINID"),
            },
        )
    if sid == "gdacs":
        typ = p.get("eventtype")
        category = {
            "EQ": Category.EARTHQUAKE,
            "WF": Category.OTHER,
            "FL": Category.FLOOD,
            "TC": Category.WEATHER,
        }.get(typ, Category.OTHER)
        occurred = timestamp(p.get("fromdate"))
        updated = timestamp(p.get("datemodified") or p.get("todate"), occurred)
        return EventIn(
            source_id=sid,
            external_id=f"{typ}:{p['eventid']}",
            title=p.get("name") or p.get("description") or f"GDACS {typ}",
            category=category,
            severity={"Green": 1, "Orange": 2, "Red": 3}.get(p.get("alertlevel"), 0),
            source_severity=p.get("alertlevel", "Unknown"),
            occurred_at=occurred,
            updated_at=updated,
            expires_at=timestamp(p.get("todate"), occurred) + timedelta(days=3),
            geometry=geom,
            precision="event location; not an impact boundary",
            confidence="official",
            evidence_url=(p.get("url") or {}).get("report", "https://www.gdacs.org/")
            if isinstance(p.get("url"), dict)
            else (p.get("url") or "https://www.gdacs.org/"),
            properties={"eventtype": typ, "country": p.get("country")},
        )
    cfg = source.get("config", {})
    ext = feature.get("id") or p.get(cfg.get("id_field", "id"))
    if ext is None:
        raise ValueError("Generic feature needs a stable id or configured id_field")
    occurred = timestamp(p.get(cfg.get("time_field", "occurred_at")))
    return EventIn(
        source_id=sid,
        external_id=str(ext),
        title=str(p.get(cfg.get("title_field", "title")) or source["name"]),
        category=Category(source["category"]),
        severity=int(p.get(cfg.get("severity_field", "severity"), 0)),
        source_severity=str(p.get("source_severity", "Unknown")),
        occurred_at=occurred,
        updated_at=timestamp(p.get(cfg.get("updated_field", "updated_at")), occurred),
        expires_at=timestamp(p.get("expires_at"), occurred + timedelta(days=7)),
        status=p.get("status", "active"),
        geometry=geom,
        precision=p.get("precision", "source supplied"),
        evidence_url=str(p.get("url") or source["url"]),
        description=str(p.get("description") or ""),
        confidence="unknown",
    )


def add_feature(batch: Batch, source: dict[str, Any], feature: dict[str, Any]) -> None:
    try:
        batch.events.append(normalize(source, feature))
    except (ValueError, KeyError, TypeError, OverflowError):
        batch.rejected += 1


def fetch_arcgis(source: dict[str, Any], fetcher: Fetcher) -> Batch:
    batch = Batch()
    cfg = source.get("config", {})
    # Fetch stable object IDs first: avoids offset pagination skipping records during updates.
    base = source["url"].rstrip("/") + "/query"
    data = fetcher.get(
        base, {"where": cfg.get("where", "1=1"), "returnIdsOnly": "true", "f": "json"}
    ).json()
    if "error" in data or "objectIds" not in data:
        raise ValueError("ArcGIS object ID query failed")
    ids = sorted(data["objectIds"] or [])
    batch.raw.append(data)
    for offset in range(0, len(ids), 200):
        page = fetcher.get(
            base,
            {
                "objectIds": ",".join(map(str, ids[offset : offset + 200])),
                "outFields": "*",
                "outSR": "4326",
                "returnGeometry": "true",
                "f": "geojson",
            },
        ).json()
        if "error" in page or page.get("exceededTransferLimit"):
            raise ValueError("ArcGIS returned an error or incomplete page")
        batch.raw.append(page)
        for feature in page["features"]:
            add_feature(batch, source, feature)
    batch.checkpoint = {"fetched_at": now().isoformat(), "object_count": len(ids)}
    return batch


def fetch_geojson(source: dict[str, Any], fetcher: Fetcher) -> Batch:
    batch = Batch()
    url: str | None = source["url"]
    visited: set[str] = set()
    zone_cache: dict[str, Any] = {}
    params = source.get("config", {}).get("params", {})
    while url:
        if url in visited or len(visited) >= 100:
            raise ValueError("Source pagination loop or page limit reached")
        visited.add(url)
        page = fetcher.get(url, params).json()
        batch.raw.append(page)
        if page.get("type") != "FeatureCollection":
            raise ValueError("Source did not return a GeoJSON FeatureCollection")
        for original in page["features"]:
            feature = deepcopy(original)
            # Never present a partial zone union as the complete warning boundary.
            if source["id"] == "nws" and not feature.get("geometry"):
                zones = feature.get("properties", {}).get("affectedZones", [])
                polygons = []
                complete = bool(zones) and len(zones) <= 200
                for zone in zones if complete else []:
                    try:
                        if zone not in zone_cache:
                            zone_cache[zone] = fetcher.get(zone).json().get("geometry")
                        g = zone_cache[zone]
                        if g and g["type"] == "Polygon":
                            polygons.append(g["coordinates"])
                        elif g and g["type"] == "MultiPolygon":
                            polygons.extend(g["coordinates"])
                        else:
                            complete = False
                    except (ValueError, KeyError, httpx.HTTPError):
                        zone_cache[zone] = None
                        complete = False
                if complete and polygons:
                    from shapely.geometry import mapping, shape
                    from shapely.ops import unary_union

                    feature["geometry"] = mapping(
                        unary_union(
                            [shape({"type": "Polygon", "coordinates": p}) for p in polygons]
                        )
                    )
                    feature["properties"]["zone_geometry_resolved"] = True
            add_feature(batch, source, feature)
        url = page.get("pagination", {}).get("next")
        if not url:
            url = next(
                (link["href"] for link in page.get("links", []) if link.get("rel") == "next"), None
            )
        params = {}
    batch.checkpoint = {"fetched_at": now().isoformat(), "pages": len(visited)}
    return batch


def fetch_firms(source: dict[str, Any], fetcher: Fetcher) -> Batch:
    key = settings().firms_key
    if not key:
        raise ValueError("NASA FIRMS requires WATCH_FIRMS_KEY (free NASA map key)")
    # CONUS + Alaska + Hawaii in one bounding rectangle; no global firehose on an 8 GB host.
    url = (
        f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/VIIRS_NOAA20_NRT/-180,18,-60,72/1"
    )
    rows = list(csv.DictReader(io.StringIO(fetcher.get(url).text)))
    if rows and "latitude" not in rows[0]:
        raise ValueError("FIRMS response is not detection data")
    batch = Batch(raw=[rows])
    for row in rows:
        try:
            date = datetime.strptime(
                row["acq_date"] + row["acq_time"].zfill(4), "%Y-%m-%d%H%M"
            ).replace(tzinfo=UTC)
            lon, lat = float(row["longitude"]), float(row["latitude"])
            ext = f"{row.get('satellite', 'NOAA20')}:{date.isoformat()}:{lat}:{lon}"
            batch.events.append(
                EventIn(
                    source_id=source["id"],
                    external_id=ext,
                    title="Satellite thermal anomaly",
                    category=Category.HOTSPOT,
                    severity=1,
                    source_severity=f"Detection confidence {row.get('confidence', 'unknown')}",
                    occurred_at=date,
                    updated_at=date,
                    expires_at=date + timedelta(days=2),
                    geometry={"type": "Point", "coordinates": [lon, lat]},
                    precision="375 m nominal sensor footprint; not a fire boundary",
                    confidence="sensor",
                    evidence_url="https://firms.modaps.eosdis.nasa.gov/map/",
                    description="A thermal anomaly may be wildfire, prescribed burning, or another heat source.",
                    properties={"frp": row.get("frp"), "sensor_confidence": row.get("confidence")},
                )
            )
        except (ValueError, KeyError):
            batch.rejected += 1
    batch.checkpoint = {"fetched_at": now().isoformat()}
    return batch


def fetch_rss(source: dict[str, Any], fetcher: Fetcher) -> Batch:
    text = fetcher.get(source["url"]).text
    feed = feedparser.parse(text)
    if feed.bozo and not feed.entries:
        raise ValueError("Invalid RSS/Atom feed")
    batch = Batch(raw=[{"xml": text}])
    for entry in feed.entries:
        try:
            date_tuple = entry.get("published_parsed") or entry.get("updated_parsed")
            if not date_tuple:
                raise ValueError("Feed entry missing publication time")
            date = datetime(*date_tuple[:6]).replace(tzinfo=UTC)
            geo = None
            where = entry.get("where", {})
            if where.get("type") == "Point":
                geo = {"type": "Point", "coordinates": list(where["coordinates"])}
            batch.events.append(
                EventIn(
                    source_id=source["id"],
                    external_id=entry.get("id") or entry["link"],
                    title=entry.get("title", source["name"]),
                    category=Category(source["category"]),
                    severity=0,
                    source_severity="Unrated report",
                    occurred_at=date,
                    updated_at=date,
                    expires_at=date + timedelta(days=3),
                    geometry=geo,
                    precision="source geotag" if geo else "unlocated report",
                    evidence_url=entry.get("link", ""),
                    confidence="reported",
                    description=entry.get("summary", "")[:12000],
                )
            )
        except (ValueError, KeyError, TypeError):
            batch.rejected += 1
    batch.checkpoint = {"fetched_at": now().isoformat()}
    return batch


def fetch_gdelt(source: dict[str, Any], fetcher: Fetcher) -> Batch:
    """Read incremental 15-minute event exports; action-country US and CAMEO 14/18/19/20.

    Download newest batches with a bounded one-day replay on restart; never infer an event
    location from the publisher country or treat article-count as severity.
    """
    import zipfile

    # GDELT 2.0 adds ADM2 columns: ActionGeo type=51, name=52, country=53, lat=56, lon=57.
    checkpoint = source.get("checkpoint", {}).get("last_file", "")
    listing = fetcher.get("https://data.gdeltproject.org/gdeltv2/lastupdate.txt").text
    latest = next(
        line.split()[-1].replace("http://", "https://")
        for line in listing.splitlines()
        if line.endswith(".export.CSV.zip")
    )
    latest_time = datetime.strptime(latest.rsplit("/", 1)[1][:14], "%Y%m%d%H%M%S").replace(
        tzinfo=UTC
    )
    previous_time = (
        datetime.strptime(checkpoint.rsplit("/", 1)[1][:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
        if checkpoint
        else latest_time - timedelta(hours=2)
    )
    start = max(previous_time + timedelta(minutes=15), latest_time - timedelta(days=1))
    candidates = []
    while start <= latest_time:
        candidates.append(
            f"https://data.gdeltproject.org/gdeltv2/{start:%Y%m%d%H%M%S}.export.CSV.zip"
        )
        start += timedelta(minutes=15)
    batch = Batch()
    for url in candidates[-8:] if not checkpoint else candidates[:8]:
        content = fetcher.get(url).content
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            member = z.infolist()[0]
            if member.file_size > 64 * 1024 * 1024:
                raise ValueError("GDELT archive exceeds expansion limit")
            text = z.read(member).decode("utf-8")
        accepted = []
        for row in csv.reader(io.StringIO(text), delimiter="\t"):
            try:
                if len(row) < 61 or row[53] != "US" or row[28] not in {"14", "18", "19", "20"}:
                    continue
                date = datetime.strptime(row[1], "%Y%m%d").replace(tzinfo=UTC)
                seen = datetime.strptime(row[59], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
                geo = (
                    {"type": "Point", "coordinates": [float(row[57]), float(row[56])]}
                    if row[51] in {"3", "4"} and row[56] and row[57]
                    else None
                )
                peaceful = row[28] == "14"
                batch.events.append(
                    EventIn(
                        source_id=source["id"],
                        external_id=row[0],
                        title=f"{'Demonstration' if peaceful else 'Conflict'} reported — {row[52]}",
                        category=Category.UNREST,
                        severity=1 if peaceful else 2,
                        source_severity=f"CAMEO {row[26]}",
                        occurred_at=date,
                        updated_at=seen,
                        expires_at=date + timedelta(days=3),
                        geometry=geo,
                        precision=f"news-coded location (GDELT type {row[51]}); unverified",
                        evidence_url=row[60],
                        confidence="reported",
                        description="Automated news coding; verify the underlying report before acting.",
                        properties={
                            "cameo": row[26],
                            "mentions": row[31],
                            "location_type": row[51],
                        },
                    )
                )
                accepted.append(row)
            except (ValueError, IndexError):
                batch.rejected += 1
        batch.raw.append({"file": url, "us_records": accepted})
        batch.checkpoint["last_file"] = url
    if not candidates:
        batch.checkpoint = source.get("checkpoint", {}).copy()
    batch.checkpoint["data_updated_at"] = latest_time.isoformat()
    batch.checkpoint["coverage_note"] = (
        "Rolling exports: initial two-hour replay; recovery limited to one day. Earlier coverage is unavailable."
    )
    if candidates and batch.checkpoint.get("last_file") != latest:
        batch.checkpoint["coverage_note"] += " Catch-up is still in progress."
    return batch


def fetch(source: dict[str, Any], fetcher: Fetcher) -> Batch:
    adapter = source["adapter"]
    handler = {
        "geojson": fetch_geojson,
        "arcgis": fetch_arcgis,
        "firms": fetch_firms,
        "rss": fetch_rss,
        "gdelt": fetch_gdelt,
    }[adapter]
    batch = handler(source, fetcher)
    # A completely incompatible payload is a failed collection, not successful empty coverage.
    if batch.rejected and not batch.events:
        raise ValueError(f"All {batch.rejected} source records failed validation")
    return batch
