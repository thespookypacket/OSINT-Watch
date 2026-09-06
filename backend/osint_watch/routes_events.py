import base64
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from . import contracts as out
from .db import connection, required_row
from .security import require
from .store import EVENT_SELECT, feature

router = APIRouter(dependencies=[Depends(require())], tags=["Events"])


def predicates(
    bbox: str | None,
    category: str | None,
    source: str | None,
    since: datetime | None,
    until: datetime | None,
    active: bool,
    lon: float | None = None,
    lat: float | None = None,
    radius_km: float = 25,
) -> tuple[str, list[Any]]:
    clauses = ["s.export_allowed"]
    args: list[Any] = []
    if bbox:
        try:
            a, b, c, d = [float(x) for x in bbox.split(",")]
            if not (-180 <= a <= c <= 180 and -90 <= b <= d <= 90):
                raise ValueError()
        except ValueError as exc:
            raise HTTPException(
                422, "bbox must be west,south,east,north in WGS84; split antimeridian queries"
            ) from exc
        clauses.append("e.geom && ST_MakeEnvelope(%s,%s,%s,%s,4326)")
        args.extend([a, b, c, d])
    if category:
        clauses.append("e.category=ANY(%s)")
        args.append(category.split(","))
    if source:
        clauses.append("e.source_id=ANY(%s)")
        args.append(source.split(","))
    for value, expression in [(since, "e.updated_at>=%s"), (until, "e.updated_at<=%s")]:
        if value:
            if value.tzinfo is None:
                raise HTTPException(422, "Time filters must include a timezone")
            clauses.append(expression)
            args.append(value)
    if active:
        clauses.append("e.status='active' AND (e.expires_at IS NULL OR e.expires_at>now())")
    if lon is not None or lat is not None:
        if lon is None or lat is None or not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise HTTPException(422, "Provide valid lon and lat together")
        clauses.append(
            "ST_DWithin(e.geom::geography,ST_SetSRID(ST_MakePoint(%s,%s),4326)::geography,%s)"
        )
        args.extend([lon, lat, radius_km * 1000])
    return " AND ".join(clauses), args


@router.get("/events", response_model=out.EventPage)
def list_events(
    bbox: str | None = None,
    category: str | None = None,
    source: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    active: bool = True,
    limit: int = Query(100, ge=1, le=1000),
    cursor: str | None = None,
    lon: float | None = None,
    lat: float | None = None,
    radius_km: float = Query(25, ge=0, le=1000),
):
    where, args = predicates(bbox, category, source, since, until, active, lon, lat, radius_km)
    if cursor:
        try:
            data = json.loads(base64.urlsafe_b64decode(cursor))
            timestamp = datetime.fromisoformat(data[0])
            identifier = UUID(data[1])
        except (ValueError, TypeError, IndexError, KeyError) as exc:
            raise HTTPException(422, "Invalid pagination cursor") from exc
        where += " AND (e.updated_at,e.id)<(%s,%s)"
        args.extend([timestamp, identifier])
    with connection() as conn:
        rows = conn.execute(
            EVENT_SELECT + " WHERE " + where + " ORDER BY e.updated_at DESC,e.id DESC LIMIT %s",
            args + [limit + 1],
        ).fetchall()
    page = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        next_cursor = base64.urlsafe_b64encode(
            json.dumps([page[-1]["updated_at"].isoformat(), str(page[-1]["id"])]).encode()
        ).decode()
    return {
        "type": "FeatureCollection",
        "features": [feature(r) for r in page],
        "next_cursor": next_cursor,
    }


@router.get("/events/changes", response_model=out.Changes)
def changes(cursor: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=1000)):
    with connection() as conn:
        floor = required_row(conn.execute("SELECT floor FROM sync_state").fetchone())["floor"]
        if cursor < floor:
            raise HTTPException(
                410,
                "Cursor expired; capture /events/sync-state cursor, take a full snapshot, then resume changes from that cursor",
            )
        # Read every sequence to advance over restricted sources without exposing their identifiers.
        rows = conn.execute(
            "SELECT c.*,s.export_allowed FROM changes c JOIN sources s ON s.id=c.source_id WHERE seq>%s ORDER BY seq LIMIT %s",
            (cursor, limit),
        ).fetchall()
        result = [
            {
                "cursor": r["seq"],
                "id": str(r["event_id"]),
                "operation": r["operation"],
                "feature": r["feature"],
            }
            for r in rows
            if r["export_allowed"]
        ]
    return {
        "changes": result,
        "next_cursor": rows[-1]["seq"] if rows else cursor,
        "has_more": len(rows) == limit,
    }


@router.get("/events/sync-state", response_model=out.SyncState)
def sync_state():
    with connection() as conn:
        return conn.execute(
            "SELECT greatest(coalesce((SELECT max(seq) FROM changes),0),floor) AS cursor,floor FROM sync_state"
        ).fetchone()


@router.get("/events/{event_id}", response_model=out.EventDetail)
def event_detail(event_id: UUID):
    with connection() as conn:
        row = conn.execute(
            EVENT_SELECT + " WHERE e.id=%s AND s.export_allowed", (event_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Event not found")
        revisions = conn.execute(
            "SELECT seq,operation,created_at,feature FROM changes WHERE event_id=%s ORDER BY seq DESC LIMIT 30",
            (event_id,),
        ).fetchall()
        related = conn.execute(
            """SELECT e.id,e.title,l.reason FROM event_links l JOIN events e
            ON e.id=CASE WHEN l.event_a=%s THEN l.event_b ELSE l.event_a END JOIN sources s ON s.id=e.source_id
            WHERE (l.event_a=%s OR l.event_b=%s) AND s.export_allowed""",
            (event_id, event_id, event_id),
        ).fetchall()
        exposures = conn.execute(
            "SELECT a.*,s.name AS asset_name FROM alerts a JOIN assets s ON s.id=a.asset_id WHERE event_id=%s",
            (event_id,),
        ).fetchall()
        return {
            "event": feature(row),
            "revisions": revisions,
            "related": related,
            "exposures": exposures,
        }


@router.get("/tiles/{z}/{x}/{y}.pbf")
def tiles(
    z: int,
    x: int,
    y: int,
    category: str | None = None,
    since: datetime | None = None,
    source: str | None = None,
    until: datetime | None = None,
):
    if not 0 <= z <= 16 or not (0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(422, "Invalid tile coordinate")
    where, args = predicates(None, category, source, since, until, True)
    with connection() as conn:
        row = required_row(
            conn.execute(
                """WITH bounds AS (SELECT ST_TileEnvelope(%s,%s,%s) AS geom), data AS (
            SELECT e.id::text AS id,e.title,e.category,e.severity,e.source_id,
            ST_AsMVTGeom(ST_Transform(e.geom,3857),bounds.geom,4096,64,true) AS geom
            FROM events e JOIN sources s ON s.id=e.source_id CROSS JOIN bounds WHERE """
                + where
                + """
            AND e.geom && ST_Transform(ST_Expand(bounds.geom,(ST_XMax(bounds.geom)-ST_XMin(bounds.geom))*64/4096),4326)
            ) SELECT ST_AsMVT(data,'events',4096,'geom') AS tile FROM data""",
                [z, x, y] + args,
            ).fetchone()
        )
    return Response(bytes(row["tile"] or b""), media_type="application/vnd.mapbox-vector-tile")


@router.get("/dashboard", response_model=out.Dashboard)
def dashboard(
    since: datetime | None = None, category: str | None = None, source: str | None = None
):
    where, args = predicates(None, category, source, since, None, True)
    with connection() as conn:
        categories = conn.execute(
            "SELECT e.category,count(*) AS count FROM events e JOIN sources s ON s.id=e.source_id WHERE "
            + where
            + " GROUP BY e.category",
            args,
        ).fetchall()
        exposures = required_row(
            conn.execute(
                """SELECT count(DISTINCT a.asset_id) AS exposed_assets,
            count(*) FILTER(WHERE a.status='open') AS open_alerts FROM alerts a JOIN events e ON e.id=a.event_id
            JOIN sources s ON s.id=e.source_id WHERE a.status<>'resolved' AND """
                + where,
                args,
            ).fetchone()
        )
        trends = conn.execute(
            "SELECT date_trunc('day',e.occurred_at) AS day,count(*) AS count FROM events e JOIN sources s ON s.id=e.source_id WHERE "
            + where
            + " GROUP BY 1 ORDER BY 1",
            args,
        ).fetchall()
        return {
            "active_events": sum(r["count"] for r in categories),
            **exposures,
            "categories": categories,
            "trends": trends,
        }
