"""Wire contracts. Hazard semantics are deliberately separate from source confidence."""

import math
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from shapely.errors import GEOSException
from shapely.geometry import shape


class Category(StrEnum):
    WILDFIRE = "wildfire_perimeter"
    HOTSPOT = "satellite_hotspot"
    FIRE_WEATHER = "fire_weather"
    WEATHER = "severe_weather"
    FLOOD = "flood"
    EARTHQUAKE = "earthquake"
    UNREST = "reported_unrest"
    OTHER = "other_hazard"


def now() -> datetime:
    return datetime.now(UTC)


def validate_geometry(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    try:
        geom = shape(value)
    except (GEOSException, KeyError, TypeError) as exc:
        raise ValueError("Malformed GeoJSON geometry") from exc
    if geom.geom_type not in {
        "Point",
        "MultiPoint",
        "Polygon",
        "MultiPolygon",
        "LineString",
        "MultiLineString",
    }:
        raise ValueError("Use a point, line, or polygon geometry")
    if geom.is_empty or not geom.is_valid:
        raise ValueError("Geometry is empty or invalid; repair self-intersections before importing")
    a, b, c, d = geom.bounds
    if not all(math.isfinite(n) for n in geom.bounds) or a < -180 or c > 180 or b < -90 or d > 90:
        raise ValueError("Coordinates must be WGS84 longitude/latitude")
    return value


class EventIn(BaseModel):
    source_id: str
    external_id: str
    title: str
    category: Category
    severity: int = Field(default=0, ge=0, le=4)
    source_severity: str = "Unknown"
    status: Literal["active", "expired", "cancelled"] = "active"
    occurred_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
    geometry: dict[str, Any] | None = None
    precision: str = "unknown"
    evidence_url: str = ""
    description: str = ""
    confidence: Literal["official", "sensor", "reported", "unknown"] = "unknown"
    properties: dict[str, Any] = Field(default_factory=dict)

    _geometry = field_validator("geometry")(validate_geometry)

    @field_validator("occurred_at", "updated_at", "expires_at")
    @classmethod
    def timezone_required(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Timestamp must include a timezone")
        return value


class AssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    geometry: dict[str, Any]
    radius_km: float = Field(default=25, ge=0, le=1000)
    min_severity: int = Field(default=2, ge=0, le=4)
    categories: list[Category] = Field(default_factory=lambda: [c for c in Category])
    domains: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("geometry")
    @classmethod
    def asset_geometry(cls, value: dict[str, Any]) -> dict[str, Any]:
        validate_geometry(value)
        if value["type"] not in {"Point", "Polygon", "MultiPolygon"}:
            raise ValueError("Assets must be sites (Point) or areas (Polygon/MultiPolygon)")
        return value


class SourceIn(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{1,39}$")
    name: str = Field(min_length=1, max_length=120)
    adapter: Literal["geojson", "arcgis", "rss"]
    url: str
    category: Category = Category.OTHER
    attribution: str = Field(min_length=1)
    export_allowed: bool = False
    interval_seconds: int = Field(default=900, ge=60, le=86400)
    config: dict[str, Any] = Field(default_factory=dict)


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[Literal["read", "write", "admin"]] = Field(default=["read"])
    days: int = Field(default=90, ge=1, le=365)


class WebhookIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    url: str


class LoginIn(BaseModel):
    username: str
    password: str
