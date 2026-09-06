import { useEffect, useState, type FormEvent } from "react";
import type { Geometry } from "geojson";
import { Pencil, Trash2, Upload, MapPin, Plus, Search } from "lucide-react";
import { api, post, useResource } from "../api";
import NetBoxSync from "../components/NetBoxSync";
import { categories, type Asset, type List } from "../types";
import {
  Button,
  Confirm,
  Empty,
  Field,
  Modal,
  StatusMessage,
} from "../components/ui";
export function AssetEditor({
  asset,
  geometry,
  onClose,
  onSaved,
}: {
  asset?: Asset;
  geometry?: Geometry;
  onClose: () => void;
  onSaved: () => void;
}) {
  const point =
    (asset?.geometry || geometry)?.type === "Point"
      ? ((asset?.geometry || geometry) as {
          type: "Point";
          coordinates: number[];
        })
      : null;
  const [name, setName] = useState(asset?.name || "");
  const [lon, setLon] = useState(point?.coordinates[0]?.toFixed(5) || "");
  const [lat, setLat] = useState(point?.coordinates[1]?.toFixed(5) || "");
  const [radius, setRadius] = useState(String(asset?.radius_km ?? 25));
  const [severity, setSeverity] = useState(String(asset?.min_severity ?? 2));
  const [domains, setDomains] = useState(asset?.domains.join(", ") || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<string[]>(
    asset?.categories || Object.keys(categories),
  );
  const [discard, setDiscard] = useState(false);
  const area =
    (asset?.geometry.type !== "Point" && asset?.geometry) ||
    (geometry?.type !== "Point" && geometry);
  const close = () => {
    if (name || lon || lat) setDiscard(true);
    else onClose();
  };
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, []);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (!name.trim() || (!area && (!lon || !lat))) {
      setError("Enter a name and valid longitude and latitude.");
      return;
    }
    setBusy(true);
    try {
      const body = {
        name,
        geometry: area || {
          type: "Point",
          coordinates: [Number(lon), Number(lat)],
        },
        radius_km: Number(radius),
        min_severity: Number(severity),
        categories: selected,
        domains: domains
          .split(",")
          .map((v) => v.trim())
          .filter(Boolean),
      };
      await api("/assets" + (asset ? "/" + asset.id : ""), {
        method: asset ? "PUT" : "POST",
        body: JSON.stringify(body),
      });
      onSaved();
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={asset ? "Edit asset" : "Add asset"} onClose={close}>
      <form noValidate onSubmit={submit}>
        <Field
          disabled={!!asset?.external_source}
          label="Asset name"
          value={name}
          autoFocus
          onChange={(e) => setName(e.target.value)}
          required
          error={error && !name ? "A name is required" : undefined}
        />
        {asset?.external_source ? (
          <p className="muted">
            Name and coordinates are managed by NetBox. Edit exposure rules
            here; change the location in NetBox.
          </p>
        ) : null}
        {area ? (
          <p className="message">
            Area boundary selected. Exposure evaluates this polygon and its
            surrounding radius.
          </p>
        ) : (
          <div className="form-grid">
            <Field
              disabled={!!asset?.external_source}
              label="Longitude"
              type="number"
              step="any"
              value={lon}
              onChange={(e) => setLon(e.target.value)}
              placeholder="-104.9903"
            />
            <Field
              disabled={!!asset?.external_source}
              label="Latitude"
              type="number"
              step="any"
              value={lat}
              onChange={(e) => setLat(e.target.value)}
              placeholder="39.7392"
            />
          </div>
        )}
        <div className="form-grid">
          <Field
            label="Proximity radius (km)"
            type="number"
            min="0"
            max="1000"
            value={radius}
            onChange={(e) => setRadius(e.target.value)}
          />
          <label className="field">
            Minimum severity
            <select
              value={severity}
              onChange={(e) => setSeverity(e.target.value)}
            >
              <option value="0">Unknown and above</option>
              <option value="1">Low and above</option>
              <option value="2">Moderate and above</option>
              <option value="3">High and above</option>
              <option value="4">Extreme only</option>
            </select>
          </label>
        </div>
        <fieldset>
          <legend>Monitor categories</legend>
          <div className="check-grid">
            {Object.entries(categories).map(([id, c]) => (
              <label key={id}>
                <input
                  type="checkbox"
                  checked={selected.includes(id)}
                  onChange={() =>
                    setSelected((prev) =>
                      prev.includes(id)
                        ? prev.filter((v) => v !== id)
                        : [...prev, id],
                    )
                  }
                />
                {c.label}
              </label>
            ))}
          </div>
        </fieldset>
        <Field
          label="Associated domains or IPs (comma separated, optional)"
          value={domains}
          onChange={(e) => setDomains(e.target.value)}
        />
        <StatusMessage error>{error}</StatusMessage>
        <div className="actions">
          <Button type="button" onClick={close}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" busy={busy}>
            Save asset
          </Button>
        </div>
      </form>
      {discard ? (
        <Confirm
          title="Discard changes"
          onClose={() => setDiscard(false)}
          onConfirm={async () => onClose()}
        >
          Close this form without saving the entered asset details?
        </Confirm>
      ) : null}
    </Modal>
  );
}
export default function Assets({
  revision,
  onChange,
  onAdd,
}: {
  revision: number;
  onChange: () => void;
  onAdd: () => void;
}) {
  const [offset, setOffset] = useState(0);
  const { data, error, loading } = useResource<List<Asset>>(
    "/assets?limit=20&offset=" + offset,
    revision,
  );
  const [edit, setEdit] = useState<Asset>();
  const [remove, setRemove] = useState<Asset>();
  const [importing, setImporting] = useState(false);
  const [text, setText] = useState("");
  const [format, setFormat] = useState("csv");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [importError, setImportError] = useState("");
  const [scanAsset, setScanAsset] = useState<Asset>();
  const [target, setTarget] = useState("");
  return (
    <>
      <NetBoxSync onChange={onChange} />
      <div className="section-toolbar">
        <p className="muted">Fixed sites and areas, with rules you control.</p>
        <div className="actions">
          <Button onClick={() => setImporting(true)}>
            <Upload size={16} />
            Import assets
          </Button>
          <Button variant="primary" onClick={onAdd}>
            <Plus size={16} />
            Add asset
          </Button>
        </div>
      </div>
      <StatusMessage error>{error}</StatusMessage>
      <StatusMessage>{message}</StatusMessage>
      <div className="panel">
        <div className="panel-heading">
          <h2>Saved locations</h2>
          <span className="muted">{data?.total ?? 0} assets</span>
        </div>
        {loading && !data ? (
          <p className="padded">Loading assets…</p>
        ) : data?.items.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Geometry</th>
                  <th>Radius</th>
                  <th>Minimum severity</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <MapPin size={15} />
                      {a.name}
                      {a.external_source ? (
                        <small>
                          NetBox ·{" "}
                          {a.sync_state === "current"
                            ? "Synced site"
                            : a.sync_state === "missing"
                              ? "Missing upstream — monitoring paused"
                              : "Coordinates unavailable — monitoring paused"}
                        </small>
                      ) : null}
                    </td>
                    <td>{a.geometry.type === "Point" ? "Site" : "Area"}</td>
                    <td>{a.radius_km} km</td>
                    <td>{a.min_severity}/4</td>
                    <td>
                      <div className="actions">
                        <Button
                          aria-label={"Edit " + a.name}
                          variant="ghost"
                          onClick={() => setEdit(a)}
                        >
                          <Pencil size={16} />
                        </Button>
                        <Button
                          aria-label={"Enrich " + a.name}
                          variant="ghost"
                          onClick={() => {
                            setScanAsset(a);
                            setTarget(a.domains[0] || "");
                          }}
                        >
                          <Search size={16} />
                        </Button>
                        <Button
                          aria-label={"Delete " + a.name}
                          variant="ghost"
                          onClick={() => setRemove(a)}
                        >
                          <Trash2 size={16} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="Start with a place that matters">
            Add a site, draw an area on the map, or import your locations.
            Exposure appears when a matching event is nearby.
          </Empty>
        )}
        <div className="pagination">
          <Button
            disabled={!offset}
            onClick={() => setOffset(Math.max(0, offset - 20))}
          >
            Previous
          </Button>
          <span>
            {data?.total ? offset + 1 : 0}–
            {Math.min(offset + 20, data?.total || 0)}
          </span>
          <Button
            disabled={offset + 20 >= (data?.total || 0)}
            onClick={() => setOffset(offset + 20)}
          >
            Next
          </Button>
        </div>
      </div>
      {edit ? (
        <AssetEditor
          asset={edit}
          onClose={() => setEdit(undefined)}
          onSaved={() => {
            onChange();
            setMessage("Asset saved. Exposure rules recalculated.");
          }}
        />
      ) : null}
      {remove ? (
        <Confirm
          title="Delete asset"
          onClose={() => setRemove(undefined)}
          onConfirm={async () => {
            await api("/assets/" + remove.id, { method: "DELETE" });
            setOffset(0);
            onChange();
            setMessage("Asset deleted.");
          }}
        >
          Delete “{remove.name}” and its exposure alerts? Source events remain
          available.
        </Confirm>
      ) : null}
      {importing ? (
        <Modal title="Import assets" onClose={() => setImporting(false)}>
          <p>
            CSV columns: name, longitude, latitude, radius_km, min_severity.
            GeoJSON features require a name property.
          </p>
          <label className="field">
            Format
            <select value={format} onChange={(e) => setFormat(e.target.value)}>
              <option value="csv">CSV</option>
              <option value="geojson">GeoJSON</option>
            </select>
          </label>
          <label className="field">
            Choose a file
            <input
              type="file"
              accept=".csv,.json,.geojson"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (file) {
                  if (file.size > 4_000_000) {
                    setImportError("File exceeds 4 MB");
                    return;
                  }
                  setText(await file.text());
                }
              }}
            />
          </label>
          <label className="field">
            Or paste file contents
            <textarea
              className="resize-none"
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={8}
              style={{ resize: "none" }}
            />
          </label>
          <StatusMessage error>{importError}</StatusMessage>
          <div className="actions">
            <Button onClick={() => setImporting(false)}>Cancel</Button>
            <Button
              variant="primary"
              busy={busy}
              onClick={async () => {
                setBusy(true);
                setImportError("");
                try {
                  const r = await post<{ created: number }>("/assets/import", {
                    format,
                    content: text,
                  });
                  setMessage(`${r.created} assets imported.`);
                  setImporting(false);
                  onChange();
                } catch (e) {
                  setImportError((e as Error).message);
                } finally {
                  setBusy(false);
                }
              }}
            >
              Import assets
            </Button>
          </div>
        </Modal>
      ) : null}
      {scanAsset ? (
        <Modal
          title="Passive enrichment"
          onClose={() => setScanAsset(undefined)}
        >
          <p>
            Request a passive SpiderFoot scan for a domain or IP attached to{" "}
            {scanAsset.name}. This does not affect physical hazard alerts.
          </p>
          <label className="field">
            Target
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              {scanAsset.domains.map((d) => (
                <option key={d}>{d}</option>
              ))}
            </select>
          </label>
          {!scanAsset.domains.length ? (
            <p>Edit this asset to attach a domain or IP first.</p>
          ) : null}
          <StatusMessage error>{importError}</StatusMessage>
          <Button
            variant="primary"
            disabled={!target}
            busy={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await post("/enrichment", { asset_id: scanAsset.id, target });
                setMessage(
                  "Enrichment queued. Track progress in Settings → Jobs.",
                );
                setScanAsset(undefined);
              } catch (e) {
                setImportError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Request passive scan
          </Button>
        </Modal>
      ) : null}
    </>
  );
}
