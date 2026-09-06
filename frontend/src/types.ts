import type { Feature, Geometry } from "geojson";
export const categories = {
  wildfire_perimeter: { label: "Wildfire perimeters", color: "#c44914" },
  satellite_hotspot: { label: "Satellite hotspots", color: "#dc7820" },
  fire_weather: { label: "Fire-weather warnings", color: "#926000" },
  severe_weather: { label: "Weather alerts", color: "#a16c00" },
  flood: { label: "Flood alerts", color: "#267c9d" },
  earthquake: { label: "Earthquakes", color: "#285bb5" },
  reported_unrest: { label: "Reported unrest", color: "#865a91" },
  other_hazard: { label: "Other hazards", color: "#687685" },
} as const;
export type Category = keyof typeof categories;
export interface EventProperties {
  title: string;
  category: Category;
  severity: number;
  source_severity: string;
  source_id: string;
  attribution: string;
  status: string;
  occurred_at: string;
  updated_at: string;
  ingested_at: string;
  expires_at: string | null;
  precision: string;
  evidence_url: string;
  description: string;
  confidence: string;
  properties: Record<string, unknown>;
}
export type EventFeature = Feature<Geometry | null, EventProperties> & {
  id: string;
};
export interface EventPage {
  type: "FeatureCollection";
  features: EventFeature[];
  next_cursor: string | null;
}
export interface Asset {
  external_source?: string | null;
  external_instance?: string | null;
  external_id?: string | null;
  sync_state?: "current" | "missing" | "unlocated" | null;
  last_synced_at?: string | null;
  id: string;
  name: string;
  geometry: Geometry;
  radius_km: number;
  min_severity: number;
  categories: Category[];
  domains: string[];
}
export interface Source {
  id: string;
  name: string;
  adapter: string;
  category: Category;
  attribution: string;
  export_allowed: boolean;
  enabled: boolean;
  interval_seconds: number;
  last_attempt: string | null;
  last_success: string | null;
  last_error: string | null;
  rejected_count: number;
  event_count: number;
  health: string;
  coverage_note?: string | null;
}
export interface Exposure {
  id: string;
  event_id: string;
  asset_id: string;
  asset_name: string;
  title: string;
  category: Category;
  severity: number;
  confidence: string;
  source_id: string;
  reason: string;
  distance_km: number;
  status: string;
  created_at: string;
}
export interface Dashboard {
  active_events: number;
  exposed_assets: number;
  open_alerts: number;
  categories: { category: Category; count: number }[];
  trends: { day: string; count: number }[];
}
export interface Settings {
  basemap_url: string;
  ai_enabled: boolean;
  spiderfoot_enabled: boolean;
  retention_days: number;
  raw_retention_days: number;
  version: string;
}
export interface EventDetail {
  event: EventFeature;
  revisions: { seq: number; operation: string; created_at: string }[];
  related: { id: string; title: string; reason: string }[];
  exposures: Exposure[];
}
export interface Job {
  id: string;
  kind: string;
  status: string;
  attempts: number;
  error: string | null;
  result?: { summary?: string; evidence_ids?: string[]; output?: string };
}
export interface Credential {
  id: string;
  name: string;
  scopes: string[];
  expires_at: string;
  revoked_at: string | null;
}
export interface Webhook {
  id: string;
  name: string;
  url: string;
  enabled: boolean;
}
export interface List<T> {
  items: T[];
  total?: number;
}
