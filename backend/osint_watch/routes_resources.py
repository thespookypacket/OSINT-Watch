import csv
import io
import ipaddress
import json
import re
import secrets
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from . import contracts as out
from .config import settings
from .connectors.base import validate_url
from .db import connection, required_row
from .models import AssetIn, SourceIn, TokenIn, WebhookIn
from .routes_events import predicates
from .security import audit, issue_token, require
from .store import enqueue, notify_alert, refresh_exposure

router = APIRouter(tags=["Workspace"])


def asset_write(conn, body: AssetIn, identifier: UUID | None = None):
    params = (
        body.name,
        json.dumps(body.geometry),
        body.radius_km,
        body.min_severity,
        [c.value for c in body.categories],
        body.domains,
    )
    if identifier:
        row = conn.execute(
            "UPDATE assets SET name=CASE WHEN external_source IS NULL THEN %s ELSE name END,geom=CASE WHEN external_source IS NULL THEN ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)) ELSE geom END,radius_km=%s,min_severity=%s,categories=%s,domains=%s,updated_at=now() WHERE id=%s RETURNING id",
            params + (identifier,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Asset not found")
    else:
        row = conn.execute(
            "INSERT INTO assets(name,geom,radius_km,min_severity,categories,domains) VALUES (%s,ST_Force2D(ST_SetSRID(ST_GeomFromGeoJSON(%s),4326)),%s,%s,%s,%s) RETURNING id",
            params,
        ).fetchone()
    return row


@router.get("/assets", response_model=out.Items[out.Asset], dependencies=[Depends(require())])
def assets(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    with connection() as conn:
        rows = conn.execute(
            "SELECT id,name,ST_AsGeoJSON(geom,15)::jsonb AS geometry,radius_km,min_severity,categories,domains,external_source,external_instance,external_id,sync_state,last_synced_at FROM assets ORDER BY name,id LIMIT %s OFFSET %s",
            (limit, offset),
        ).fetchall()
        total = required_row(conn.execute("SELECT count(*) AS n FROM assets").fetchone())["n"]
    return {"items": rows, "total": total}


@router.post("/assets", status_code=201, response_model=out.Identifier)
def create_asset(body: AssetIn, credential=Depends(require("write"))):
    with connection() as conn:
        row = asset_write(conn, body)
        audit(conn, credential["id"], "asset.create", row["id"])
        refresh_exposure(conn)
    return row


@router.put("/assets/{asset_id}")
def update_asset(asset_id: UUID, body: AssetIn, credential=Depends(require("write"))):
    with connection() as conn:
        row = asset_write(conn, body, asset_id)
        audit(conn, credential["id"], "asset.update", asset_id)
        refresh_exposure(conn)
    return row


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: UUID, credential=Depends(require("write"))):
    with connection() as conn:
        row = conn.execute("DELETE FROM assets WHERE id=%s RETURNING id", (asset_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Asset not found")
        audit(conn, credential["id"], "asset.delete", asset_id)
    return {"ok": True}


class ImportIn(BaseModel):
    format: str
    content: str = Field(max_length=4_000_000)


@router.post("/assets/import", status_code=201, response_model=out.ImportResult)
def import_assets(body: ImportIn, credential=Depends(require("write"))):
    candidates = []
    try:
        if body.format == "csv":
            for row in csv.DictReader(io.StringIO(body.content)):
                candidates.append(
                    AssetIn(
                        name=row["name"],
                        geometry={
                            "type": "Point",
                            "coordinates": [float(row["longitude"]), float(row["latitude"])],
                        },
                        radius_km=float(row.get("radius_km") or 25),
                        min_severity=int(row.get("min_severity") or 2),
                    )
                )
        elif body.format == "geojson":
            data = json.loads(body.content)
            features = data["features"] if data["type"] == "FeatureCollection" else [data]
            for f in features:
                candidates.append(AssetIn(**{**f.get("properties", {}), "geometry": f["geometry"]}))
        else:
            raise ValueError("Choose csv or geojson")
        if not 1 <= len(candidates) <= 1000:
            raise ValueError("Import must contain 1–1000 assets")
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(
            422,
            "Import rejected; no assets saved. Check names, WGS84 coordinates, geometry validity, and numeric rule values.",
        ) from exc
    with connection() as conn:
        rows = [asset_write(conn, candidate) for candidate in candidates]
        refresh_exposure(conn)
        audit(conn, credential["id"], "asset.import", len(rows))
    return {"created": len(rows), "items": rows}


@router.get("/alerts", response_model=out.Items[out.Exposure], dependencies=[Depends(require())])
@router.get("/exposure", response_model=out.Items[out.Exposure], dependencies=[Depends(require())])
def alerts(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    since: datetime | None = None,
    category: str | None = None,
    source: str | None = None,
):
    where, args = predicates(None, category, source, since, None, False)
    if status:
        where += " AND a.status=%s"
        args.append(status)
    base = (
        " FROM alerts a JOIN assets t ON t.id=a.asset_id JOIN events e ON e.id=a.event_id JOIN sources s ON s.id=e.source_id WHERE "
        + where
    )
    with connection() as conn:
        total = required_row(conn.execute("SELECT count(*) AS n" + base, args).fetchone())["n"]
        rows = conn.execute(
            "SELECT a.*,t.name AS asset_name,e.title,e.category,e.severity,e.confidence,e.source_id,s.attribution"
            + base
            + " ORDER BY a.updated_at DESC,a.id LIMIT %s OFFSET %s",
            args + [limit, offset],
        ).fetchall()
    return {"items": rows, "total": total}


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge(alert_id: UUID, credential=Depends(require("write"))):
    with connection() as conn:
        row = conn.execute(
            """UPDATE alerts SET status='acknowledged',acknowledged_at=now(),updated_at=now()
            WHERE id=%s AND status='open' AND event_id IN (SELECT e.id FROM events e JOIN sources s ON s.id=e.source_id WHERE s.export_allowed) RETURNING id,updated_at""",
            (alert_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Active alert not found")
        audit(conn, credential["id"], "alert.acknowledge", alert_id)
        notify_alert(conn, row)
    return row


@router.get("/sources", response_model=out.Sources, dependencies=[Depends(require())])
def sources():
    with connection() as conn:
        rows = conn.execute("""SELECT id,name,adapter,category,attribution,export_allowed,enabled,interval_seconds,
            last_attempt,last_success,last_error,rejected_count,event_count,checkpoint->>'coverage_note' AS coverage_note,
            CASE WHEN NOT enabled THEN 'disabled' WHEN last_success IS NULL THEN 'missing'
            WHEN last_error IS NOT NULL THEN 'error'
            WHEN id='gdelt' AND (checkpoint->>'data_updated_at')::timestamptz<now()-interval '1 hour' THEN 'stale'
            WHEN last_success<now()-interval '1 second'*greatest(interval_seconds*3,900) THEN 'stale'
            WHEN rejected_count>0 THEN 'degraded' ELSE 'healthy' END AS health FROM sources ORDER BY name""").fetchall()
        heartbeat = conn.execute("SELECT heartbeat FROM worker_health WHERE id='worker'").fetchone()
    for row in rows:
        if row["id"] == "firms" and not settings().firms_key:
            row["health"] = "key_required"
    return {"items": rows, "worker_heartbeat": heartbeat["heartbeat"] if heartbeat else None}


@router.post("/sources", status_code=201, response_model=out.SourceIdentifier)
def create_source(body: SourceIn, credential=Depends(require("admin"))):
    try:
        validate_url(body.url, settings().allowed_outbound_hosts)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, "Feed URL must resolve to an allowed HTTP(S) destination") from exc
    with connection() as conn:
        if conn.execute("SELECT 1 FROM sources WHERE id=%s", (body.id,)).fetchone():
            raise HTTPException(409, "Source ID already exists")
        conn.execute(
            "INSERT INTO sources(id,name,adapter,url,category,attribution,export_allowed,interval_seconds,config) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                body.id,
                body.name,
                body.adapter,
                body.url,
                body.category.value,
                body.attribution,
                body.export_allowed,
                body.interval_seconds,
                Jsonb(body.config),
            ),
        )
        audit(conn, credential["id"], "source.create", body.id)
    return {"id": body.id}


@router.patch("/sources/{source_id}")
def toggle_source(
    source_id: str, enabled: bool = Body(embed=True), credential=Depends(require("admin"))
):
    with connection() as conn:
        row = conn.execute(
            "UPDATE sources SET enabled=%s,next_run=now() WHERE id=%s RETURNING id",
            (enabled, source_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Source not found")
        audit(conn, credential["id"], "source.enable" if enabled else "source.disable", source_id)
    return row


@router.post("/sources/{source_id}/refresh", status_code=202, response_model=out.Identifier)
def refresh_source(source_id: str, credential=Depends(require("admin"))):
    with connection() as conn:
        source = conn.execute(
            "SELECT * FROM sources WHERE id=%s FOR UPDATE", (source_id,)
        ).fetchone()
        if not source or not source["enabled"]:
            raise HTTPException(409, "Enable an existing source before refreshing it")
        existing = conn.execute(
            "SELECT id FROM jobs WHERE kind='collect' AND payload->>'source_id'=%s AND status IN ('pending','running')",
            (source_id,),
        ).fetchone()
        identifier = (
            existing["id"] if existing else enqueue(conn, "collect", {"source_id": source_id})
        )
    return {"id": identifier}


@router.get(
    "/tokens", response_model=out.Items[out.Credential], dependencies=[Depends(require("admin"))]
)
def tokens():
    with connection() as conn:
        return {
            "items": conn.execute(
                "SELECT id,name,scopes,expires_at,revoked_at FROM credentials WHERE kind='api' ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        }


@router.post("/tokens", status_code=201, response_model=out.Token)
def create_token(body: TokenIn, credential=Depends(require("admin"))):
    with connection() as conn:
        result = issue_token(conn, body.name, list(body.scopes), body.days)
        audit(conn, credential["id"], "token.create", result["id"])
    return result


@router.delete("/tokens/{token_id}")
def revoke_token(token_id: UUID, credential=Depends(require("admin"))):
    with connection() as conn:
        conn.execute(
            "UPDATE credentials SET revoked_at=now() WHERE id=%s AND kind='api'", (token_id,)
        )
        audit(conn, credential["id"], "token.revoke", token_id)
    return {"ok": True}


@router.get(
    "/webhooks", response_model=out.Items[out.Webhook], dependencies=[Depends(require("admin"))]
)
def webhooks():
    with connection() as conn:
        return {
            "items": conn.execute(
                "SELECT id,name,url,enabled FROM webhooks ORDER BY name LIMIT 100"
            ).fetchall()
        }


@router.post("/webhooks", status_code=201, response_model=out.NewWebhook)
def create_webhook(body: WebhookIn, credential=Depends(require("admin"))):
    try:
        validate_url(body.url, settings().allowed_outbound_hosts)
    except (ValueError, OSError) as exc:
        raise HTTPException(422, "Webhook must resolve to an allowed HTTP(S) destination") from exc
    secret = secrets.token_urlsafe(32)
    with connection() as conn:
        row = required_row(
            conn.execute(
                "INSERT INTO webhooks(name,url,secret) VALUES (%s,%s,%s) RETURNING id",
                (body.name, body.url, secret),
            ).fetchone()
        )
        audit(conn, credential["id"], "webhook.create", row["id"])
    return {**row, "secret": secret}


@router.delete("/webhooks/{webhook_id}")
def disable_webhook(webhook_id: UUID, credential=Depends(require("admin"))):
    with connection() as conn:
        conn.execute("UPDATE webhooks SET enabled=false WHERE id=%s", (webhook_id,))
        audit(conn, credential["id"], "webhook.disable", webhook_id)
    return {"ok": True}


@router.get("/jobs", response_model=out.Items[out.Job], dependencies=[Depends(require("admin"))])
def jobs(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    with connection() as conn:
        return {
            "items": conn.execute(
                "SELECT id,kind,status,attempts,error,created_at,finished_at FROM jobs ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (limit, offset),
            ).fetchall()
        }


@router.get("/jobs/{job_id}", response_model=out.Job, dependencies=[Depends(require("admin"))])
def job_detail(job_id: UUID):
    with connection() as conn:
        row = conn.execute(
            "SELECT id,kind,status,attempts,error,result FROM jobs WHERE id=%s", (job_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Job not found")
        if row["kind"] == "summary" and row.get("result"):
            evidence = row["result"].get("evidence_ids", [])
            visible = conn.execute(
                "SELECT e.id FROM events e JOIN sources s ON s.id=e.source_id WHERE e.id=ANY(%s::uuid[]) AND s.export_allowed",
                (evidence,),
            ).fetchall()
            if len(visible) != len(set(evidence)):
                row["result"] = None
                row["error"] = "Summary evidence is no longer available for export"
        return row


class SummaryIn(BaseModel):
    event_ids: list[UUID] = Field(min_length=1, max_length=10)


@router.post("/summaries", status_code=202, response_model=out.Identifier)
def create_summary(body: SummaryIn, credential=Depends(require("admin"))):
    if not settings().ollama_url:
        raise HTTPException(409, "Configure WATCH_OLLAMA_URL to enable local summaries")
    with connection() as conn:
        identifier = enqueue(conn, "summary", {"event_ids": [str(i) for i in body.event_ids]})
    return {"id": identifier}


class EnrichmentIn(BaseModel):
    asset_id: UUID
    target: str = Field(max_length=253)


@router.post("/enrichment", status_code=202, response_model=out.Identifier)
def enrichment(body: EnrichmentIn, credential=Depends(require("admin"))):
    if not settings().spiderfoot_url:
        raise HTTPException(409, "Enable the optional SpiderFoot profile first")
    try:
        ipaddress.ip_address(body.target)
    except ValueError:
        if not re.fullmatch(
            r"(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}",
            body.target,
        ):
            raise HTTPException(422, "Target must be a domain or IP address") from None
    with connection() as conn:
        asset = conn.execute("SELECT domains FROM assets WHERE id=%s", (body.asset_id,)).fetchone()
        if not asset or body.target not in asset["domains"]:
            raise HTTPException(
                422, "Attach this domain/IP to the saved asset before requesting enrichment"
            )
        identifier = enqueue(
            conn, "enrichment", {"asset_id": str(body.asset_id), "target": body.target}
        )
        audit(conn, credential["id"], "enrichment.request", identifier)
    return {"id": identifier}


@router.get(
    "/integrations/netbox", dependencies=[Depends(require())], response_model=out.NetBoxStatus
)
def netbox_status():
    cfg = settings()
    with connection() as conn:
        row = required_row(
            conn.execute("SELECT * FROM integration_sync WHERE id='netbox'").fetchone()
        )
        job = conn.execute(
            "SELECT id,status,error FROM jobs WHERE kind='netbox' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    return {
        **row,
        "configured": bool(cfg.netbox_url and cfg.netbox_token),
        "interval_seconds": cfg.netbox_interval_seconds,
        "job": job,
    }


@router.post("/integrations/netbox/sync", status_code=202, response_model=out.Identifier)
def request_netbox_sync(credential=Depends(require("admin"))):
    from .netbox import queue_sync

    if not settings().netbox_url or not settings().netbox_token:
        raise HTTPException(
            409,
            "Configure WATCH_NETBOX_URL and WATCH_NETBOX_TOKEN, then recreate the API and worker",
        )
    with connection() as conn:
        identifier = queue_sync(conn)
        audit(conn, credential["id"], "netbox.sync", identifier)
    return {"id": identifier}
