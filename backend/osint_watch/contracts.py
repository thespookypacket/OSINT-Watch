"""Documented API output schemas for typed clients and GIS integrations."""

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .models import AssetIn, Category

T = TypeVar("T")


class Items(BaseModel, Generic[T]):
    items: list[T]
    total: int | None = None


class Identifier(BaseModel):
    id: UUID


class SourceIdentifier(BaseModel):
    id: str


class Ok(BaseModel):
    ok: bool


class Asset(AssetIn):
    id: UUID
    external_source: str | None = None
    external_instance: str | None = None
    external_id: str | None = None
    sync_state: str | None = None
    last_synced_at: datetime | None = None


class NetBoxResult(BaseModel):
    received: int
    created: int
    updated: int
    unlocated: int
    missing: int


class NetBoxJob(BaseModel):
    id: UUID
    status: str
    error: str | None


class NetBoxStatus(BaseModel):
    configured: bool
    interval_seconds: int
    last_attempt: datetime | None
    last_success: datetime | None
    next_run: datetime
    last_error: str | None
    result: NetBoxResult | None
    job: NetBoxJob | None


class EventProperties(BaseModel):
    source_id: str
    external_id: str
    title: str
    category: Category
    severity: int
    source_severity: str
    status: Literal["active", "cancelled", "expired"]
    occurred_at: datetime
    updated_at: datetime
    ingested_at: datetime
    expires_at: datetime | None
    precision: str
    evidence_url: str
    description: str
    confidence: str
    attribution: str
    properties: dict[str, Any]


class Feature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: UUID
    geometry: dict[str, Any] | None
    properties: EventProperties


class EventPage(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature]
    next_cursor: str | None


class Change(BaseModel):
    cursor: int
    id: UUID
    operation: Literal["upsert", "delete"]
    feature: Feature | None


class Changes(BaseModel):
    changes: list[Change]
    next_cursor: int
    has_more: bool


class SyncState(BaseModel):
    cursor: int
    floor: int


class Revision(BaseModel):
    seq: int
    operation: Literal["upsert", "delete"]
    created_at: datetime
    feature: Feature | None


class Related(Identifier):
    title: str
    reason: str


class Alert(BaseModel):
    id: UUID
    asset_id: UUID
    event_id: UUID
    reason: str
    distance_km: float
    status: Literal["open", "acknowledged", "resolved"]
    created_at: datetime
    updated_at: datetime
    acknowledged_at: datetime | None
    asset_name: str


class Exposure(Alert):
    title: str
    category: Category
    severity: int
    confidence: str
    source_id: str
    attribution: str


class EventDetail(BaseModel):
    event: Feature
    revisions: list[Revision]
    related: list[Related]
    exposures: list[Alert]


class CategoryCount(BaseModel):
    category: Category
    count: int


class Trend(BaseModel):
    day: datetime
    count: int


class Dashboard(BaseModel):
    active_events: int
    exposed_assets: int
    open_alerts: int
    categories: list[CategoryCount]
    trends: list[Trend]


class Source(BaseModel):
    id: str
    name: str
    adapter: str
    category: Category
    attribution: str
    export_allowed: bool
    enabled: bool
    interval_seconds: int
    last_attempt: datetime | None
    last_success: datetime | None
    last_error: str | None
    rejected_count: int
    event_count: int
    health: str
    coverage_note: str | None = None


class Sources(BaseModel):
    items: list[Source]
    worker_heartbeat: datetime | None


class ImportResult(BaseModel):
    created: int
    items: list[Identifier]


class Credential(Identifier):
    name: str
    scopes: list[str]
    expires_at: datetime
    revoked_at: datetime | None


class Token(Identifier):
    token: str
    scopes: list[str]
    expires_at: datetime


class Webhook(Identifier):
    name: str
    url: str
    enabled: bool


class NewWebhook(Identifier):
    secret: str


class Job(Identifier):
    kind: str
    status: str
    attempts: int
    error: str | None
    model_config = ConfigDict(extra="allow")
