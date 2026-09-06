import { useEffect, useRef, useState } from "react";
import maplibregl, {
  type GeoJSONSource,
  type Map as MapInstance,
} from "maplibre-gl";
import type { FeatureCollection, Geometry, Position } from "geojson";
import "maplibre-gl/dist/maplibre-gl.css";
import { Crosshair, Home, Layers, MapPin, Pentagon, Undo2 } from "lucide-react";
import { api } from "../api";
import { categories, type Asset, type EventPage } from "../types";
import { Button } from "./ui";
interface Props {
  styleUrl: string;
  query: string;
  revision: number;
  assets: Asset[];
  onSelect: (id: string) => void;
  onPlace?: (geometry: Geometry) => void;
}
const colorExpression: maplibregl.ExpressionSpecification = [
  "match",
  ["get", "category"],
  "wildfire_perimeter",
  categories.wildfire_perimeter.color,
  ...Object.entries(categories)
    .filter(([id]) => id !== "wildfire_perimeter")
    .flatMap(([id, c]) => [id, c.color]),
  "#687685",
];
export default function HazardMap({
  styleUrl,
  query,
  revision,
  assets,
  onSelect,
  onPlace,
}: Props) {
  const node = useRef<HTMLDivElement>(null);
  const map = useRef<MapInstance | null>(null);
  const camera = useRef({
    center: [-98, 38] as [number, number],
    zoom: 3.3,
    bearing: 0,
    pitch: 0,
  });
  const select = useRef(onSelect);
  select.current = onSelect;
  const place = useRef(onPlace);
  place.current = onPlace;
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"site" | "area" | null>(null);
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const points = useRef<Position[]>([]);
  const [pointCount, setPointCount] = useState(0);
  const [opacity, setOpacity] = useState(0.75);
  const [layersOpen, setLayersOpen] = useState(true);
  const [visible, setVisible] = useState<Set<string>>(
    new Set(Object.keys(categories)),
  );
  const [dense, setDense] = useState(false);
  const [clusterRevision, setClusterRevision] = useState(0);
  useEffect(() => {
    if (!node.current) return;
    const m = new maplibregl.Map({
      container: node.current,
      style: styleUrl,
      ...camera.current,
      attributionControl: { compact: true },
      transformRequest: (url) => ({ url, credentials: "same-origin" }),
    });
    map.current = m;
    m.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "bottom-left",
    );
    m.addControl(new maplibregl.ScaleControl(), "bottom-left");
    m.on("error", () =>
      setError("A map layer could not load. Event lists remain available."),
    );
    m.on("load", () => {
      m.addSource("assets", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });
      m.addLayer({
        id: "asset-area",
        type: "fill",
        source: "assets",
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": "#16796b", "fill-opacity": 0.12 },
      });
      m.addLayer({
        id: "asset-point",
        type: "circle",
        source: "assets",
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-radius": 7,
          "circle-color": "#16796b",
          "circle-stroke-color": "#fff",
          "circle-stroke-width": 2,
        },
      });
      m.addSource("draft", {
        type: "geojson",
        data:
          points.current.length > 1
            ? {
                type: "Feature",
                properties: {},
                geometry: {
                  type: "LineString",
                  coordinates: [...points.current],
                },
              }
            : { type: "FeatureCollection", features: [] },
      });
      m.addLayer({
        id: "draft-line",
        type: "line",
        source: "draft",
        paint: { "line-color": "#16796b", "line-width": 3 },
      });
      m.on("click", (e) => {
        if (modeRef.current === "site") {
          place.current?.({
            type: "Point",
            coordinates: [e.lngLat.lng, e.lngLat.lat],
          });
          setMode(null);
          return;
        }
        if (modeRef.current === "area") {
          points.current.push([e.lngLat.lng, e.lngLat.lat]);
          setPointCount(points.current.length);
          (m.getSource("draft") as GeoJSONSource).setData({
            type: "Feature",
            properties: {},
            geometry: { type: "LineString", coordinates: points.current },
          });
          return;
        }
        const layers = ["hazard-fill", "hazard-point", "unclustered"].filter(
          (l) => m.getLayer(l),
        );
        const hit = m.queryRenderedFeatures(e.point, { layers })[0];
        if (hit?.properties?.id) select.current(String(hit.properties.id));
      });
      setReady(true);
    });
    return () => {
      setReady(false);
      camera.current = {
        center: m.getCenter().toArray(),
        zoom: m.getZoom(),
        bearing: m.getBearing(),
        pitch: m.getPitch(),
      };
      m.remove();
      map.current = null;
    };
  }, [styleUrl]);
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    (m.getSource("assets") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: assets
        .filter((a) => !a.external_source || a.sync_state === "current")
        .map((a) => ({
          type: "Feature",
          geometry: a.geometry,
          properties: { name: a.name },
        })),
    });
  }, [assets, ready]);
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    const params = new URLSearchParams(query);
    params.set("revision", String(revision));
    const url =
      new URL("/api/v1/tiles/{z}/{x}/{y}.pbf", location.origin).href
        .replaceAll("%7B", "{")
        .replaceAll("%7D", "}") +
      "?" +
      params.toString();
    for (const id of ["hazard-fill", "hazard-outline", "hazard-point"])
      if (m.getLayer(id)) m.removeLayer(id);
    if (m.getSource("hazards")) m.removeSource("hazards");
    m.addSource("hazards", {
      type: "vector",
      tiles: [url],
      minzoom: 0,
      maxzoom: 16,
    });
    m.addLayer({
      id: "hazard-fill",
      type: "fill",
      source: "hazards",
      "source-layer": "events",
      filter: ["==", ["geometry-type"], "Polygon"],
      paint: { "fill-color": colorExpression, "fill-opacity": 0.25 },
    });
    m.addLayer({
      id: "hazard-outline",
      type: "line",
      source: "hazards",
      "source-layer": "events",
      filter: ["==", ["geometry-type"], "Polygon"],
      paint: { "line-color": colorExpression, "line-width": 1.4 },
    });
    m.addLayer({
      id: "hazard-point",
      type: "circle",
      source: "hazards",
      "source-layer": "events",
      filter: ["==", ["geometry-type"], "Point"],
      paint: {
        "circle-color": colorExpression,
        "circle-radius": 5,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 1.5,
      },
    });
    let controller = new AbortController();
    const load = async () => {
      controller.abort();
      controller = new AbortController();
      const bounds = m.getBounds();
      const q = new URLSearchParams(query);
      q.set("limit", "1000");
      q.set(
        "bbox",
        [
          Math.max(-180, bounds.getWest()),
          Math.max(-90, bounds.getSouth()),
          Math.min(180, bounds.getEast()),
          Math.min(90, bounds.getNorth()),
        ].join(","),
      );
      try {
        const page = await api<EventPage>("/events?" + q, {
          signal: controller.signal,
        });
        setDense(!!page.next_cursor);
        const features: FeatureCollection = {
          type: "FeatureCollection",
          features: page.next_cursor
            ? []
            : page.features.flatMap((f) =>
                f.geometry?.type === "Point"
                  ? [
                      {
                        ...f,
                        geometry: f.geometry,
                        properties: { ...f.properties, id: f.id },
                      },
                    ]
                  : [],
              ),
        };
        if (m.getSource("clusters"))
          (m.getSource("clusters") as GeoJSONSource).setData(features);
        else {
          m.addSource("clusters", {
            type: "geojson",
            data: features,
            cluster: true,
            clusterRadius: 35,
            clusterMaxZoom: 8,
          });
          m.addLayer({
            id: "unclustered",
            type: "circle",
            source: "clusters",
            filter: ["!", ["has", "point_count"]],
            paint: {
              "circle-color": colorExpression,
              "circle-radius": 5,
              "circle-stroke-color": "#fff",
              "circle-stroke-width": 1.5,
            },
          });
          m.addLayer({
            id: "cluster-count",
            type: "circle",
            source: "clusters",
            filter: ["has", "point_count"],
            paint: {
              "circle-color": "#122333",
              "circle-radius": 17,
              "circle-stroke-color": "white",
              "circle-stroke-width": 2,
            },
          });
          m.addLayer({
            id: "cluster-label",
            type: "symbol",
            source: "clusters",
            filter: ["has", "point_count"],
            layout: {
              "text-field": ["get", "point_count_abbreviated"],
              "text-size": 11,
            },
            paint: { "text-color": "#ffffff" },
          });
          m.on("click", "cluster-count", async (e) => {
            const f = e.features?.[0];
            if (f && f.geometry.type === "Point") {
              const z = await (
                m.getSource("clusters") as GeoJSONSource
              ).getClusterExpansionZoom(Number(f.properties.cluster_id));
              m.easeTo({
                center: f.geometry.coordinates as [number, number],
                zoom: z,
              });
            }
          });
        }
        setClusterRevision((n) => n + 1);
      } catch (e) {
        if ((e as Error).name !== "AbortError")
          setError(
            "Map events could not refresh. Try changing the time filter.",
          );
      }
    };
    void load();
    m.on("moveend", load);
    return () => {
      controller.abort();
      m.off("moveend", load);
    };
  }, [query, revision, ready]);
  useEffect(() => {
    const m = map.current;
    if (!m || !ready) return;
    for (const [id, kind] of [
      ["hazard-fill", "Polygon"],
      ["hazard-outline", "Polygon"],
      ["hazard-point", "Point"],
    ]) {
      if (m.getLayer(id))
        m.setFilter(id, [
          "all",
          ["==", ["geometry-type"], kind],
          ["in", ["get", "category"], ["literal", [...visible]]],
        ]);
    }
    if (m.getLayer("hazard-fill"))
      m.setPaintProperty("hazard-fill", "fill-opacity", opacity * 0.4);
    if (m.getLayer("hazard-point"))
      m.setPaintProperty("hazard-point", "circle-opacity", opacity);
    const clustered = visible.size === Object.keys(categories).length && !dense;
    if (m.getLayer("hazard-point"))
      m.setLayoutProperty(
        "hazard-point",
        "visibility",
        clustered ? "none" : "visible",
      );
    if (m.getLayer("unclustered")) {
      m.setLayoutProperty(
        "unclustered",
        "visibility",
        clustered ? "visible" : "none",
      );
      m.setPaintProperty("unclustered", "circle-opacity", opacity);
    }
    // Clusters summarize all categories and are hidden when individual layers are filtered.
    for (const id of ["cluster-count", "cluster-label"])
      if (m.getLayer(id))
        m.setLayoutProperty(
          id,
          "visibility",
          visible.size === Object.keys(categories).length && !dense
            ? "visible"
            : "none",
        );
  }, [visible, opacity, ready, query, dense, revision, clusterRevision]);
  const updateDraft = () => {
    (map.current?.getSource("draft") as GeoJSONSource)?.setData(
      points.current.length > 1
        ? {
            type: "Feature",
            properties: {},
            geometry: { type: "LineString", coordinates: [...points.current] },
          }
        : { type: "FeatureCollection", features: [] },
    );
  };
  const clearDraft = () => {
    points.current = [];
    setPointCount(0);
    updateDraft();
  };
  const finish = () => {
    if (points.current.length >= 3) {
      place.current?.({
        type: "Polygon",
        coordinates: [[...points.current, points.current[0]]],
      });
      points.current = [];
      setPointCount(0);
      setMode(null);
      (map.current?.getSource("draft") as GeoJSONSource)?.setData({
        type: "FeatureCollection",
        features: [],
      });
    }
  };
  return (
    <div className="map-wrap">
      <div
        ref={node}
        className="map-canvas"
        aria-label="Interactive public hazard map"
      />
      <div className="map-layers">
        <button
          className="layers-title"
          onClick={() => setLayersOpen(!layersOpen)}
          aria-expanded={layersOpen}
        >
          <Layers size={16} />
          Map layers<span>{layersOpen ? "−" : "+"}</span>
        </button>
        {layersOpen ? (
          <>
            <div className="layer-list">
              {Object.entries(categories).map(([id, c]) => (
                <label key={id}>
                  <input
                    type="checkbox"
                    checked={visible.has(id)}
                    onChange={() =>
                      setVisible((prev) => {
                        const n = new Set(prev);
                        if (n.has(id)) n.delete(id);
                        else n.add(id);
                        return n;
                      })
                    }
                  />
                  <span className="dot" style={{ background: c.color }} />
                  {c.label}
                </label>
              ))}
            </div>
            <label className="opacity">
              Opacity
              <input
                type="range"
                min="0.1"
                max="1"
                step="0.05"
                value={opacity}
                onChange={(e) => setOpacity(Number(e.target.value))}
              />
            </label>
          </>
        ) : null}
      </div>
      <div className="map-actions">
        <Button
          aria-label="Reset map to United States"
          onClick={() => map.current?.flyTo({ center: [-98, 38], zoom: 3.3 })}
        >
          <Home size={17} />
        </Button>
        {onPlace ? (
          <>
            <Button
              disabled={!ready}
              aria-label="Place a site on map"
              className={mode === "site" ? "selected" : ""}
              onClick={() => setMode(mode === "site" ? null : "site")}
            >
              <MapPin size={17} />
            </Button>
            <Button
              disabled={!ready}
              aria-label="Draw an area"
              className={mode === "area" ? "selected" : ""}
              onClick={() => {
                clearDraft();
                setMode(mode === "area" ? null : "area");
              }}
            >
              <Pentagon size={17} />
            </Button>
          </>
        ) : null}
      </div>
      {mode ? (
        <div className="drawing-status">
          <Crosshair size={16} />
          {mode === "site"
            ? "Click the map to place a site."
            : "Click boundary points, then finish the area."}
          {mode === "area" ? (
            <>
              <Button disabled={pointCount < 3} onClick={finish}>
                Finish area ({pointCount})
              </Button>
              <Button
                aria-label="Undo last point"
                onClick={() => {
                  points.current.pop();
                  setPointCount(points.current.length);
                  updateDraft();
                }}
              >
                <Undo2 size={16} />
              </Button>
            </>
          ) : null}
          <Button
            onClick={() => {
              setMode(null);
              clearDraft();
            }}
          >
            Cancel
          </Button>
        </div>
      ) : null}
      {error ? (
        <div className="map-error" role="status">
          {error}
        </div>
      ) : null}
    </div>
  );
}
