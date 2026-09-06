"""Transactional event revisions, exposure, and durable notification outbox."""

import hashlib
import json
from datetime import timedelta
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from .db import required_row
from .models import EventIn, now

EVENT_SELECT = """SELECT e.*,ST_AsGeoJSON(e.geom,15)::jsonb AS geometry,s.attribution,s.export_allowed
                  FROM events e JOIN sources s ON s.id=e.source_id"""


def feature(row: dict[str, Any]) -> dict[str, Any]:
    excluded = {"geom", "geometry", "fingerprint", "export_allowed", "id"}
    props = {
        k: v.isoformat() if hasattr(v, "isoformat") else v
        for k, v in row.items()
        if k not in excluded
    }
    return {
        "type": "Feature",
        "id": str(row["id"]),
        "geometry": row.get("geometry"),
        "properties": props,
    }


def enqueue(
    conn: Connection[Any], kind: str, payload: dict[str, Any], key: str | None = None
) -> Any:
    row = conn.execute(
        "INSERT INTO jobs(kind,payload,dedup_key) VALUES (%s,%s,%s) ON CONFLICT(dedup_key) DO NOTHING RETURNING id",
        (kind, Jsonb(payload), key),
    ).fetchone()
    return row["id"] if row else None


def record_change(conn: Connection[Any], event_id: Any, operation: str = "upsert") -> int:
    row = required_row(conn.execute(EVENT_SELECT + " WHERE e.id=%s", (event_id,)).fetchone())
    change = required_row(
        conn.execute(
            "INSERT INTO changes(event_id,source_id,operation,feature) VALUES (%s,%s,%s,%s) RETURNING seq",
            (
                event_id,
                row["source_id"],
                operation,
                Jsonb(feature(row)) if operation == "upsert" else None,
            ),
        ).fetchone()
    )
    return change["seq"]


def upsert_event(conn: Connection[Any], event: EventIn) -> bool:
    body = event.model_dump(mode="json")
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    # Serialize writes and change sequence assignment: committed cursors cannot skip late commits.
    conn.execute("SELECT pg_advisory_xact_lock(701925)")
    old = conn.execute(
        "SELECT id,fingerprint,updated_at FROM events WHERE source_id=%s AND external_id=%s",
        (event.source_id, event.external_id),
    ).fetchone()
    if old and (old["fingerprint"] == fingerprint or old["updated_at"] > event.updated_at):
        return False
    geom = json.dumps(event.geometry) if event.geometry else None
    fields = (
        event.source_id,
        event.external_id,
        event.title,
        event.category.value,
        event.severity,
        event.source_severity,
        event.status,
        event.occurred_at,
        event.updated_at,
        event.expires_at,
        geom,
        event.precision,
        event.evidence_url,
        event.description,
        event.confidence,
        Jsonb(event.properties),
        fingerprint,
    )
    row = required_row(
        conn.execute(
            """INSERT INTO events(source_id,external_id,title,category,severity,source_severity,status,
        occurred_at,updated_at,expires_at,geom,precision,evidence_url,description,confidence,properties,fingerprint)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)),%s,%s,%s,%s,%s,%s)
        ON CONFLICT(source_id,external_id) DO UPDATE SET title=excluded.title,category=excluded.category,
        severity=excluded.severity,source_severity=excluded.source_severity,status=excluded.status,
        occurred_at=excluded.occurred_at,updated_at=excluded.updated_at,expires_at=excluded.expires_at,
        geom=excluded.geom,precision=excluded.precision,evidence_url=excluded.evidence_url,
        description=excluded.description,confidence=excluded.confidence,properties=excluded.properties,
        fingerprint=excluded.fingerprint,ingested_at=now() RETURNING id""",
            fields,
        ).fetchone()
    )
    event_id = row["id"]
    record_change(conn, event_id)
    # Evidence linkage is a candidate match, never a destructive merge or hotspot/perimeter match.
    conn.execute(
        """INSERT INTO event_links(event_a,event_b,reason)
        SELECT least(a.id,b.id),greatest(a.id,b.id),'Possible duplicate: same category, within 10 km and 1 hour'
        FROM events a JOIN events b ON a.source_id<>b.source_id AND a.category=b.category
        AND b.occurred_at BETWEEN a.occurred_at-interval '1 hour' AND a.occurred_at+interval '1 hour'
        AND ST_DWithin(a.geom::geography,b.geom::geography,10000)
        WHERE a.id=%s ON CONFLICT DO NOTHING""",
        (event_id,),
    )
    # Cancel/Update CAP messages reference identifiers of earlier alerts.
    if event.source_id == "nws":
        for ref in event.properties.get("references", []):
            identifier = ref.get("identifier") or ref.get("@id")
            if identifier:
                superseded = conn.execute(
                    "UPDATE events SET status='cancelled' WHERE source_id='nws' AND external_id<>%s AND (external_id=%s OR external_id LIKE %s) AND status='active' RETURNING id",
                    (event.external_id, identifier, "%" + identifier),
                ).fetchall()
                for item in superseded:
                    record_change(conn, item["id"])
    return True


def notify_alert(conn: Connection[Any], row: dict[str, Any]) -> None:
    """A versioned outbox entry makes repeated evaluation idempotent."""
    for hook in conn.execute("SELECT id FROM webhooks WHERE enabled").fetchall():
        enqueue(
            conn,
            "webhook",
            {"webhook_id": str(hook["id"]), "alert_id": str(row["id"])},
            f"alert:{row['id']}:{row['updated_at'].isoformat()}:{hook['id']}",
        )


def refresh_exposure(conn: Connection[Any]) -> None:
    matches = conn.execute("""SELECT e.id AS event_id,a.id AS asset_id,e.title,a.name,e.severity,e.category,e.confidence,
        ST_Distance(e.geom::geography,a.geom::geography)/1000 AS distance_km,
        ST_Intersects(e.geom,a.geom) AS intersects
        FROM assets a JOIN events e ON e.category=ANY(a.categories) AND e.severity>=a.min_severity
        AND e.status='active' AND (e.expires_at IS NULL OR e.expires_at>now())
        AND ST_DWithin(e.geom::geography,a.geom::geography,a.radius_km*1000)
        JOIN sources s ON s.id=e.source_id WHERE s.export_allowed AND (a.external_source IS NULL OR a.sync_state='current')""").fetchall()
    active_ids = []
    for match in matches:
        reason = (
            f"{match['category'].replace('_', ' ')} intersects {match['name']}"
            if match["intersects"]
            else f"{match['category'].replace('_', ' ')} is {match['distance_km']:.1f} km from {match['name']}"
        )
        reason += f"; severity {match['severity']}/4; evidence: {match['confidence']}"
        row = required_row(
            conn.execute(
                """INSERT INTO alerts(event_id,asset_id,reason,distance_km) VALUES (%s,%s,%s,%s)
            ON CONFLICT(event_id,asset_id) DO UPDATE SET reason=excluded.reason,distance_km=excluded.distance_km,
            status=CASE WHEN alerts.status='resolved' THEN 'open' ELSE alerts.status END,
            updated_at=CASE WHEN alerts.reason<>excluded.reason OR alerts.status='resolved' THEN now() ELSE alerts.updated_at END
            RETURNING *, (updated_at=transaction_timestamp()) AS changed""",
                (match["event_id"], match["asset_id"], reason, match["distance_km"]),
            ).fetchone()
        )
        active_ids.append(row["id"])
        if row["changed"]:
            notify_alert(conn, row)
    resolved = conn.execute(
        "UPDATE alerts SET status='resolved',updated_at=now() WHERE status<>'resolved' AND NOT(id=ANY(%s::uuid[])) RETURNING id,updated_at",
        (active_ids,),
    ).fetchall()
    for row in resolved:
        notify_alert(conn, row)


def maintenance(conn: Connection[Any], raw_days: int, event_days: int) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(701925)")
    expired = conn.execute(
        "UPDATE events SET status='expired' WHERE status='active' AND expires_at<=now() RETURNING id"
    ).fetchall()
    for row in expired:
        record_change(conn, row["id"])
    cutoff = now() - timedelta(days=event_days)
    for row in conn.execute(
        "SELECT id FROM events WHERE updated_at<%s AND status<>'active'", (cutoff,)
    ).fetchall():
        record_change(conn, row["id"], "delete")
        conn.execute("DELETE FROM events WHERE id=%s", (row["id"],))
    floor = required_row(
        conn.execute(
            "SELECT coalesce(max(seq),0) AS seq FROM changes WHERE created_at<%s", (cutoff,)
        ).fetchone()
    )["seq"]
    conn.execute("UPDATE sync_state SET floor=greatest(floor,%s)", (floor,))
    conn.execute("DELETE FROM changes WHERE seq<=%s", (floor,))
    conn.execute(
        "DELETE FROM raw_payloads WHERE fetched_at<%s", (now() - timedelta(days=raw_days),)
    )
    conn.execute("DELETE FROM rate_limits WHERE window_at<now()-interval '1 day'")
    conn.execute("DELETE FROM credentials WHERE expires_at<now()-interval '7 days'")
    conn.execute("DELETE FROM jobs WHERE finished_at<%s", (cutoff,))
    conn.execute("DELETE FROM audit_log WHERE created_at<%s", (cutoff,))
