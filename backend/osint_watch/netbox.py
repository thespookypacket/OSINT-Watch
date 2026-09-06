"""One-way, transactional NetBox site synchronization; local risk rules remain local."""

import json
import time
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from psycopg import Connection
from psycopg.types.json import Jsonb

from .config import settings
from .db import connection, required_row
from .models import AssetIn, Category
from .store import enqueue, refresh_exposure


def endpoint() -> str:
    """Operator-owned URL permits LAN NetBox, but never credentials/query/fragment."""
    base = settings().netbox_url.rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Configure a valid NetBox base URL without credentials or query parameters"
        )
    if base.endswith("/api"):
        base = base[:-4]
    return base + "/api/dcim/sites/"


def fetch_sites(transport: httpx.BaseTransport | None = None) -> list[dict[str, Any]]:
    cfg = settings()
    if not cfg.netbox_token:
        raise ValueError("Configure a read-only NetBox token")
    root = endpoint()
    scheme = "Bearer" if cfg.netbox_token.startswith("nbt_") else "Token"
    expected = urlsplit(root)
    url: str | None = root + "?limit=100"
    visited: set[str] = set()
    records: dict[int, dict[str, Any]] = {}
    expected_count: int | None = None
    deadline = time.monotonic() + 300
    with httpx.Client(
        timeout=30,
        follow_redirects=False,
        transport=transport,
        headers={"Authorization": f"{scheme} {cfg.netbox_token}", "Accept": "application/json"},
    ) as client:
        while url:
            if time.monotonic() > deadline:
                raise ValueError("NetBox sync exceeded its five-minute fetch budget")
            parsed = urlsplit(url)
            # Never send the secret to a next-page URL outside the configured endpoint.
            if (
                (parsed.scheme, parsed.netloc, parsed.path)
                != (expected.scheme, expected.netloc, expected.path)
                or parsed.fragment
                or parsed.username
            ):
                raise ValueError("NetBox pagination left the configured endpoint")
            if url in visited or len(visited) >= 100:
                raise ValueError("NetBox pagination loop or 100-page limit exceeded")
            visited.add(url)
            with client.stream("GET", url) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if time.monotonic() > deadline:
                        raise ValueError("NetBox sync exceeded its fetch budget")
                    if len(content) > 16_000_000:
                        raise ValueError("NetBox page exceeds 16 MB")
            page = json.loads(content)
            if (
                not isinstance(page, dict)
                or not isinstance(page.get("results"), list)
                or type(page.get("count")) is not int
            ):
                raise ValueError("NetBox returned an invalid list response")
            if expected_count is None:
                expected_count = page["count"]
            if expected_count != page["count"] or expected_count > 10000:
                raise ValueError(
                    "NetBox inventory changed during pagination or exceeds 10000 sites; retry"
                )
            for record in page["results"]:
                if (
                    not isinstance(record, dict)
                    or type(record.get("id")) is not int
                    or record["id"] in records
                ):
                    raise ValueError("NetBox returned invalid or duplicate site IDs")
                records[record["id"]] = record
            next_page = page.get("next")
            if next_page is not None and not isinstance(next_page, str):
                raise ValueError("Invalid NetBox pagination link")
            url = urljoin(url, next_page) if next_page else None
    if len(records) != expected_count:
        raise ValueError("Incomplete NetBox snapshot; assets were not changed")
    return list(records.values())


def queue_sync(conn: Connection[Any]) -> Any:
    conn.execute("SELECT id FROM integration_sync WHERE id='netbox' FOR UPDATE")
    pending = conn.execute(
        "SELECT id FROM jobs WHERE kind='netbox' AND status IN ('pending','running') ORDER BY created_at LIMIT 1"
    ).fetchone()
    return pending["id"] if pending else enqueue(conn, "netbox", {})


def sync_sites(transport: httpx.BaseTransport | None = None) -> dict[str, int]:
    with connection() as conn:
        conn.execute("UPDATE integration_sync SET last_attempt=now() WHERE id='netbox'")
    try:
        sites = fetch_sites(transport)
        instance = endpoint()
        valid: list[tuple[str, AssetIn]] = []
        unlocated: list[str] = []
        for site in sites:
            try:
                if site.get("latitude") is None or site.get("longitude") is None:
                    raise ValueError("Missing coordinates")
                asset = AssetIn(
                    name=site["name"],
                    geometry={
                        "type": "Point",
                        "coordinates": [float(site["longitude"]), float(site["latitude"])],
                    },
                )
                valid.append((str(site["id"]), asset))
            except (ValueError, KeyError, TypeError):
                unlocated.append(str(site["id"]))
        with connection() as conn:
            conn.execute("SELECT id FROM integration_sync WHERE id='netbox' FOR UPDATE")
            # This happens only after a complete, validated snapshot, never after a failed page.
            conn.execute("UPDATE assets SET sync_state='missing' WHERE external_source='netbox'")
            created = updated = 0
            for identifier, asset in valid:
                row = required_row(
                    conn.execute(
                        """INSERT INTO assets(name,geom,radius_km,min_severity,categories,external_source,external_instance,external_id,sync_state,last_synced_at)
                    VALUES (%s,ST_SetSRID(ST_GeomFromGeoJSON(%s),4326),25,2,%s,'netbox',%s,%s,'current',now())
                    ON CONFLICT(external_source,external_instance,external_id) DO UPDATE SET
                    name=excluded.name,geom=excluded.geom,sync_state='current',last_synced_at=now(),updated_at=now()
                    RETURNING (xmax=0) AS inserted""",
                        (
                            asset.name,
                            json.dumps(asset.geometry),
                            [c.value for c in Category],
                            instance,
                            identifier,
                        ),
                    ).fetchone()
                )
                created += int(row["inserted"])
                updated += int(not row["inserted"])
            conn.execute(
                "UPDATE assets SET sync_state='unlocated' WHERE external_source='netbox' AND external_instance=%s AND external_id=ANY(%s)",
                (instance, unlocated),
            )
            missing = required_row(
                conn.execute(
                    "SELECT count(*) AS n FROM assets WHERE external_source='netbox' AND sync_state='missing'"
                ).fetchone()
            )["n"]
            result = {
                "received": len(sites),
                "created": created,
                "updated": updated,
                "unlocated": len(unlocated),
                "missing": missing,
            }
            refresh_exposure(conn)
            conn.execute(
                "UPDATE integration_sync SET last_success=now(),last_error=NULL,result=%s WHERE id='netbox'",
                (Jsonb(result),),
            )
            return result
    except Exception as exc:
        # Do not retain HTTP exception text: it can contain upstream URLs or authentication data.
        with connection() as conn:
            conn.execute(
                "UPDATE integration_sync SET last_error=%s WHERE id='netbox'",
                (
                    f"NetBox sync failed ({type(exc).__name__}). Check URL, token, connectivity and site permissions. Previous assets were retained.",
                ),
            )
        raise
