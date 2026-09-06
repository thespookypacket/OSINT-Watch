import { useState } from "react";
import { RefreshCw, Plus } from "lucide-react";
import { api, post, timeAgo, useResource } from "../api";
import { categories, type List, type Source } from "../types";
import { Button, Field, Modal, StatusMessage } from "../components/ui";
export default function Sources({
  revision,
  onChange,
}: {
  revision: number;
  onChange: () => void;
}) {
  const { data, error } = useResource<List<Source>>("/sources", revision);
  const [message, setMessage] = useState("");
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState("");
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [id, setId] = useState("");
  const [adapter, setAdapter] = useState("geojson");
  const [category, setCategory] = useState("other_hazard");
  const [attribution, setAttribution] = useState("");
  const [exportAllowed, setExportAllowed] = useState(false);
  const [config, setConfig] = useState("{}");
  const act = async (id: string, fn: () => Promise<unknown>) => {
    setBusy(id);
    setFailure("");
    try {
      await fn();
      onChange();
      setMessage("Source updated.");
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  return (
    <>
      <div className="section-toolbar">
        <p className="muted">
          Public feeds, collection health, and attribution.
        </p>
        <Button variant="primary" onClick={() => setAdding(true)}>
          <Plus size={16} />
          Add public source
        </Button>
      </div>
      <StatusMessage error>{error || failure}</StatusMessage>
      <StatusMessage>{message}</StatusMessage>
      <div className="panel">
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Source</th>
                <th>Health</th>
                <th>Last collected</th>
                <th>Records / rejected</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((s) => (
                <tr key={s.id}>
                  <td>
                    <strong>{s.name}</strong>
                    <small>{s.attribution}</small>
                    {s.coverage_note ? <small>{s.coverage_note}</small> : null}
                    {s.last_error ? (
                      <small className="error">{s.last_error}</small>
                    ) : null}
                    {s.health === "key_required" ? (
                      <small>
                        Set WATCH_FIRMS_KEY in .env, then restart the worker.
                      </small>
                    ) : null}
                  </td>
                  <td>
                    <span className={"health " + s.health}>
                      {s.health.replaceAll("_", " ")}
                    </span>
                  </td>
                  <td>
                    {timeAgo(s.last_success)}
                    <small>Every {s.interval_seconds / 60} minutes</small>
                  </td>
                  <td>
                    {s.event_count} / {s.rejected_count}
                    <small>
                      {s.export_allowed
                        ? "Export permitted"
                        : "Export restricted"}
                    </small>
                  </td>
                  <td>
                    <div className="actions">
                      <Button
                        busy={busy === s.id}
                        disabled={!s.enabled || s.health === "key_required"}
                        onClick={() =>
                          act(s.id, () => post("/sources/" + s.id + "/refresh"))
                        }
                        aria-label={"Refresh " + s.name}
                      >
                        <RefreshCw size={15} />
                      </Button>
                      <Button
                        busy={busy === s.id}
                        onClick={() =>
                          act(s.id, () =>
                            api("/sources/" + s.id, {
                              method: "PATCH",
                              body: JSON.stringify({ enabled: !s.enabled }),
                            }),
                          )
                        }
                      >
                        {s.enabled ? "Pause" : "Enable"}
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <p className="footnote">
        Missing or stale feeds are gaps in coverage, not evidence that an area
        is safe. Satellite hotspots, reported perimeters, and fire-weather
        warnings describe different observations.
      </p>
      {adding ? (
        <Modal title="Add public source" onClose={() => setAdding(false)}>
          <form
            noValidate
            onSubmit={(e) => {
              e.preventDefault();
              void act("new", async () => {
                await post("/sources", {
                  id,
                  name,
                  url,
                  adapter,
                  category,
                  attribution,
                  export_allowed: exportAllowed,
                  config: JSON.parse(config),
                });
                setAdding(false);
              });
            }}
          >
            <div className="form-grid">
              <Field
                label="Source ID"
                value={id}
                onChange={(e) => setId(e.target.value)}
                placeholder="county-alerts"
              />
              <Field
                label="Display name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <Field
              label="Feed URL"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <div className="form-grid">
              <label className="field">
                Adapter
                <select
                  value={adapter}
                  onChange={(e) => setAdapter(e.target.value)}
                >
                  <option value="geojson">GeoJSON</option>
                  <option value="arcgis">ArcGIS FeatureServer layer</option>
                  <option value="rss">RSS / Atom</option>
                </select>
              </label>
              <label className="field">
                Category
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  {Object.entries(categories).map(([id, c]) => (
                    <option key={id} value={id}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <Field
              label="Attribution"
              value={attribution}
              onChange={(e) => setAttribution(e.target.value)}
            />
            <label className="check">
              <input
                type="checkbox"
                checked={exportAllowed}
                onChange={(e) => setExportAllowed(e.target.checked)}
              />
              The source permits exporting this data with attribution
            </label>
            <label className="field">
              Adapter configuration (JSON)
              <textarea
                className="resize-none"
                value={config}
                onChange={(e) => setConfig(e.target.value)}
                rows={4}
                style={{ resize: "none" }}
              />
            </label>
            <p className="muted">
              Generic GeoJSON requires stable IDs and timestamps. Field mappings
              are documented in the connector guide.
            </p>
            <StatusMessage error>{failure}</StatusMessage>
            <div className="actions">
              <Button type="button" onClick={() => setAdding(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" busy={busy === "new"}>
                Add source
              </Button>
            </div>
          </form>
        </Modal>
      ) : null}
    </>
  );
}
