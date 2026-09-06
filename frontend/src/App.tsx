import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { Geometry } from "geojson";
import {
  Activity,
  Map,
  Bookmark,
  Bell,
  Database,
  Settings as SettingsIcon,
  Crosshair,
  Plus,
  Flame,
  Building2,
  Radio,
  LogOut,
  ArrowUpRight,
  RefreshCw,
} from "lucide-react";
import { api, post, severityLabel, timeAgo, useResource } from "./api";
import {
  categories,
  type Asset,
  type Dashboard,
  type EventPage,
  type Exposure,
  type List,
  type Settings,
  type Source,
} from "./types";
import { Button, Empty, Field, Secret, StatusMessage } from "./components/ui";
import EventInspector from "./components/EventInspector";
import Assets, { AssetEditor } from "./pages/Assets";
import Sources from "./pages/Sources";
import SettingsPage from "./pages/Settings";
import { useTheme, themedBasemap } from "./theme";
import ThemeSelect from "./components/ThemeSelect";
const HazardMap = lazy(() => import("./components/HazardMap"));
const nav = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "map", label: "Map explorer", icon: Map },
  { id: "assets", label: "Saved assets", icon: Bookmark },
  { id: "alerts", label: "Alerts", icon: Bell },
  { id: "sources", label: "Sources", icon: Database },
  { id: "settings", label: "Settings", icon: SettingsIcon },
];
const emptyAssets: Asset[] = [];
function Login({
  onLogin,
  appearance,
}: {
  onLogin: () => void;
  appearance: React.ReactNode;
}) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <main className="login-page">
      <div className="login-brand">
        <Crosshair size={38} />
        <h1>OSINT Watch</h1>
        <p>
          Public intelligence.
          <br />
          Local perspective.
        </p>
      </div>
      <section className="login-panel">
        {appearance}
        <h2>Sign in to your watch</h2>
        <p className="muted">Your map, sources, and saved locations.</p>
        <form
          noValidate
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            try {
              await post("/auth/login", { username, password });
              onLogin();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Field
            label="Username"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <Secret
            label="Password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <StatusMessage error>{error}</StatusMessage>
          <Button variant="primary" busy={busy} type="submit">
            Sign in
          </Button>
        </form>
        <small className="muted">
          Use the administrator credentials from your deployment’s .env file.
        </small>
      </section>
    </main>
  );
}
export default function App() {
  const { mode, theme, change } = useTheme();
  const appearance = <ThemeSelect value={mode} onChange={change} />;
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  useEffect(() => {
    api("/auth/me")
      .then(() => setAuthenticated(true))
      .catch(() => setAuthenticated(false));
  }, []);
  return authenticated === null ? (
    <main className="loading-screen">Connecting to OSINT Watch…</main>
  ) : authenticated ? (
    <Workspace
      onLogout={() => setAuthenticated(false)}
      appearance={appearance}
      theme={theme}
    />
  ) : (
    <Login onLogin={() => setAuthenticated(true)} appearance={appearance} />
  );
}
function Workspace({
  onLogout,
  appearance,
  theme,
}: {
  onLogout: () => void;
  appearance: React.ReactNode;
  theme: "light" | "dark";
}) {
  const initial = new URLSearchParams(location.search);
  const [page, setPage] = useState(initial.get("page") || "overview");
  const [hours, setHours] = useState(initial.get("hours") || "24");
  const [category, setCategory] = useState(initial.get("category") || "");
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((n) => n + 1), []);
  const [alertOffset, setAlertOffset] = useState(0);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [geometry, setGeometry] = useState<Geometry>();
  const [message, setMessage] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState("");
  useEffect(() => {
    const params = new URLSearchParams({ page, hours });
    if (category) params.set("category", category);
    history.replaceState(null, "", "?" + params);
    document.title =
      (page === "overview"
        ? "Situational overview"
        : nav.find((n) => n.id === page)?.label || "Not found") +
      " · OSINT Watch";
    setCursor(null);
    setAlertOffset(0);
  }, [page, hours, category]);
  useEffect(() => {
    const timer = setInterval(refresh, 60000);
    return () => clearInterval(timer);
  }, [refresh]);
  const query = useMemo(() => {
    const q = new URLSearchParams();
    void revision; // Advance the rolling window on the refresh clock.
    if (hours !== "all")
      q.set(
        "since",
        new Date(Date.now() - Number(hours) * 3600000).toISOString(),
      );
    if (category) q.set("category", category);
    return q.toString();
  }, [hours, category, revision]);
  const settings = useResource<Settings>("/settings");
  const sources = useResource<List<Source>>("/sources", revision);
  const dashboard = useResource<Dashboard>("/dashboard?" + query, revision);
  const events = useResource<EventPage>(
    "/events?" +
      query +
      "&limit=10" +
      (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""),
    revision,
  );
  const assets = useResource<List<Asset>>("/assets?limit=1000", revision);
  const alerts = useResource<List<Exposure>>(
    "/alerts?" + query + "&limit=50&offset=" + alertOffset,
    revision,
  );
  const healthy =
    sources.data?.items.filter((s) => s.health === "healthy").length || 0;
  const sourceCount = sources.data?.items.filter((s) => s.enabled).length || 0;
  const openAlerts =
    alerts.data?.items.filter((a) => a.status !== "resolved") || [];
  const add = () => {
    setGeometry(undefined);
    setAdding(true);
  };
  const acknowledge = async (id: string) => {
    setBusy(id);
    setActionError("");
    try {
      await post("/alerts/" + id + "/acknowledge");
      refresh();
      setMessage("Alert acknowledged.");
    } catch (e) {
      setActionError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const filterControls = (
    <>
      <label className="filter-label">
        Time window
        <select
          aria-label="Time window"
          value={hours}
          onChange={(e) => setHours(e.target.value)}
        >
          <option value="24">Last 24 hours</option>
          <option value="72">Last 3 days</option>
          <option value="168">Last 7 days</option>
          <option value="all">All retained events</option>
        </select>
      </label>
      <label className="filter-label">
        Category
        <select
          aria-label="Category filter"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">All categories</option>
          {Object.entries(categories).map(([id, c]) => (
            <option key={id} value={id}>
              {c.label}
            </option>
          ))}
        </select>
      </label>
    </>
  );
  const error =
    dashboard.error ||
    events.error ||
    sources.error ||
    assets.error ||
    alerts.error ||
    settings.error;
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="?page=overview" className="brand">
          <Crosshair size={31} />
          <span>OSINT Watch</span>
        </a>
        <nav aria-label="Main navigation">
          {nav.map((n) => (
            <button
              key={n.id}
              className={page === n.id ? "active" : ""}
              aria-current={page === n.id ? "page" : undefined}
              onClick={() => {
                setPage(n.id);
                setSelected(null);
              }}
            >
              <n.icon size={21} />
              {n.label}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="workspace-label">PERSONAL WORKSPACE</span>
          <p>Self-hosted · v0.1.0</p>
          <Button
            variant="ghost"
            onClick={async () => {
              await post("/auth/logout");
              onLogout();
            }}
          >
            <LogOut size={16} />
            Sign out
          </Button>
        </div>
      </aside>
      <main className="main">
        <header className="page-header">
          <div>
            <h1>
              {page === "overview"
                ? "Situational overview"
                : nav.find((n) => n.id === page)?.label || "Page not found"}
            </h1>
            <p>Public intelligence. Local perspective.</p>
          </div>
          <div className="header-actions">
            {appearance}
            {["overview", "map", "alerts"].includes(page)
              ? filterControls
              : null}
            <Button aria-label="Refresh dashboard" onClick={refresh}>
              <RefreshCw size={17} />
            </Button>
            <Button variant="primary" onClick={add}>
              <Plus size={17} />
              Add asset
            </Button>
          </div>
        </header>
        <StatusMessage error>
          {error
            ? `${error} Existing results may be stale. Refresh to retry.`
            : actionError}
        </StatusMessage>
        <StatusMessage>{message}</StatusMessage>
        {["overview", "map"].includes(page) ? (
          <>
            <section className="metrics" aria-label="Monitoring summary">
              <div>
                <Flame />
                <span>
                  Active events
                  <strong>
                    {dashboard.data?.active_events.toLocaleString() ?? "—"}
                  </strong>
                  <small>Within selected filters</small>
                </span>
              </div>
              <div>
                <Building2 />
                <span>
                  Exposed assets
                  <strong>{dashboard.data?.exposed_assets ?? "—"}</strong>
                  <small>Matching your proximity rules</small>
                </span>
              </div>
              <div>
                <Bell />
                <span>
                  Open alerts
                  <strong>{dashboard.data?.open_alerts ?? "—"}</strong>
                  <small>Awaiting acknowledgment</small>
                </span>
              </div>
              <div>
                <Radio />
                <span>
                  Source health
                  <strong>
                    {healthy} / {sourceCount}
                  </strong>
                  <small>
                    {healthy === sourceCount && sourceCount
                      ? "All enabled feeds current"
                      : "Coverage gaps need attention"}
                  </small>
                </span>
              </div>
            </section>
            <div
              className={"overview-grid " + (page === "map" ? "map-page" : "")}
            >
              <div className="map-column">
                <Suspense
                  fallback={<div className="map-placeholder">Loading map…</div>}
                >
                  {settings.data ? (
                    <HazardMap
                      styleUrl={themedBasemap(settings.data.basemap_url, theme)}
                      query={query}
                      revision={revision}
                      assets={assets.data?.items || emptyAssets}
                      onSelect={setSelected}
                      onPlace={(g) => {
                        setGeometry(g);
                        setAdding(true);
                      }}
                    />
                  ) : null}
                </Suspense>
                <section className="panel event-table">
                  <div className="panel-heading">
                    <h2>Latest events</h2>
                    <span className="muted">
                      {events.loading
                        ? "Refreshing…"
                        : "Source-attributed reports"}
                    </span>
                  </div>
                  {events.data?.features.length ? (
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Event</th>
                            <th>Source</th>
                            <th>Severity</th>
                            <th>Updated</th>
                          </tr>
                        </thead>
                        <tbody>
                          {events.data.features.map((f) => (
                            <tr key={f.id}>
                              <td>
                                <button
                                  className="event-link"
                                  onClick={() => setSelected(f.id)}
                                >
                                  <span
                                    className="dot"
                                    style={{
                                      background:
                                        categories[f.properties.category]
                                          ?.color,
                                    }}
                                  />
                                  {f.properties.title}
                                </button>
                              </td>
                              <td>{f.properties.source_id.toUpperCase()}</td>
                              <td>
                                <span
                                  className={
                                    "severity severity-" + f.properties.severity
                                  }
                                >
                                  {severityLabel(f.properties.severity)}
                                </span>
                              </td>
                              <td className="mono nowrap">
                                {timeAgo(f.properties.updated_at)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <Empty
                      title={
                        events.loading
                          ? "Collecting your view…"
                          : "No events in this view"
                      }
                    >
                      Try a wider time window or check Sources for collection
                      status.
                    </Empty>
                  )}
                  <div className="pagination">
                    <Button disabled={!cursor} onClick={() => setCursor(null)}>
                      First page
                    </Button>
                    <span>Up to 10 events per page</span>
                    <Button
                      disabled={!events.data?.next_cursor}
                      onClick={() =>
                        setCursor(events.data?.next_cursor || null)
                      }
                    >
                      Next page
                    </Button>
                  </div>
                </section>
                <section
                  className="panel trend-panel"
                  aria-label="Event trends"
                >
                  <div className="panel-heading">
                    <h2>Event trend</h2>
                    <span className="muted">
                      Active events by occurrence day
                    </span>
                  </div>
                  <div className="trend-bars">
                    {dashboard.data?.trends.slice(-14).map((d) => (
                      <div key={d.day}>
                        <span>
                          {new Date(d.day).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                            timeZone: "UTC",
                          })}
                        </span>
                        <meter
                          min={0}
                          max={Math.max(
                            1,
                            ...(dashboard.data?.trends || []).map(
                              (t) => t.count,
                            ),
                          )}
                          value={d.count}
                          aria-label={`${d.day}: ${d.count} events`}
                        />
                        <strong>{d.count}</strong>
                      </div>
                    ))}
                    {!dashboard.data?.trends.length ? (
                      <p className="muted">No events in the selected window.</p>
                    ) : null}
                  </div>
                </section>
              </div>
              {selected ? (
                <EventInspector
                  id={selected}
                  aiEnabled={settings.data?.ai_enabled || false}
                  onClose={() => setSelected(null)}
                />
              ) : (
                <aside className="panel exposure-panel">
                  <div className="panel-heading">
                    <h2>Exposure watch</h2>
                    <button
                      className="text-button"
                      onClick={() => setPage("alerts")}
                    >
                      View all
                    </button>
                  </div>
                  {openAlerts.length ? (
                    openAlerts.slice(0, 5).map((a) => (
                      <article className="exposure-item" key={a.id}>
                        <div className="exposure-title">
                          <span
                            className="hazard-symbol"
                            style={{ color: categories[a.category]?.color }}
                          >
                            <Activity size={22} />
                          </span>
                          <div>
                            <button
                              className="event-link"
                              onClick={() => setSelected(a.event_id)}
                            >
                              {a.title}
                            </button>
                            <small>{a.asset_name}</small>
                          </div>
                        </div>
                        <p>{a.reason}</p>
                        <div className="exposure-meta">
                          <span>
                            Source<strong>{a.source_id.toUpperCase()}</strong>
                          </span>
                          <span>
                            Status<strong>{a.status}</strong>
                          </span>
                          <span>
                            Distance
                            <strong>{a.distance_km.toFixed(1)} km</strong>
                          </span>
                        </div>
                      </article>
                    ))
                  ) : (
                    <Empty
                      title={
                        assets.data?.total
                          ? "No matching exposure"
                          : "Your places, in perspective"
                      }
                    >
                      {assets.data?.total
                        ? "No current events match your asset rules. Check feed health before drawing conclusions."
                        : "Save a site or area to see nearby hazards and explainable alerts."}
                    </Empty>
                  )}
                  <button
                    className="panel-footer"
                    onClick={() => setPage("assets")}
                  >
                    Manage saved assets <ArrowUpRight size={16} />
                  </button>
                </aside>
              )}
            </div>
          </>
        ) : null}
        {page === "assets" ? (
          <Assets revision={revision} onChange={refresh} onAdd={add} />
        ) : null}
        {page === "sources" ? (
          <Sources revision={revision} onChange={refresh} />
        ) : null}
        {page === "settings" && settings.data ? (
          <SettingsPage config={settings.data} />
        ) : null}
        {page === "alerts" ? (
          <section className="panel">
            <div className="panel-heading">
              <h2>Exposure alerts</h2>
              <span>{alerts.data?.total ?? 0} total</span>
            </div>
            {alerts.data?.items.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Asset / event</th>
                      <th>Why it matters</th>
                      <th>Status</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.data.items.map((a) => (
                      <tr key={a.id}>
                        <td>
                          <strong>{a.asset_name}</strong>
                          <button
                            className="event-link"
                            onClick={() => setSelected(a.event_id)}
                          >
                            {a.title}
                          </button>
                        </td>
                        <td>{a.reason}</td>
                        <td>{a.status}</td>
                        <td>
                          <Button
                            busy={busy === a.id}
                            disabled={a.status !== "open"}
                            onClick={() => acknowledge(a.id)}
                          >
                            Acknowledge
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="No exposure alerts">
                Alerts appear when public-source events match your saved asset
                rules.
              </Empty>
            )}
            <div className="pagination">
              <Button
                disabled={!alertOffset}
                onClick={() => setAlertOffset(Math.max(0, alertOffset - 50))}
              >
                Previous alerts
              </Button>
              <span>Page {Math.floor(alertOffset / 50) + 1}</span>
              <Button
                disabled={alertOffset + 50 >= (alerts.data?.total || 0)}
                onClick={() => setAlertOffset(alertOffset + 50)}
              >
                Next alerts
              </Button>
            </div>
            {selected ? (
              <EventInspector
                id={selected}
                aiEnabled={settings.data?.ai_enabled || false}
                onClose={() => setSelected(null)}
              />
            ) : null}
          </section>
        ) : null}
        {!nav.some((n) => n.id === page) ? (
          <Empty title="Page not found">
            Choose a view from the navigation.
          </Empty>
        ) : null}
        <footer className="status-footer">
          <span>
            <i
              className={
                "status-dot " +
                (healthy === sourceCount && sourceCount ? "ok" : "warn")
              }
            />
            {healthy === sourceCount && sourceCount
              ? "Enabled feeds current"
              : "Source coverage incomplete"}
          </span>
          <button className="text-button" onClick={() => setPage("sources")}>
            Sources online: {healthy}/{sourceCount}
          </button>
          <span>Public data · Source-dependent latency</span>
        </footer>
      </main>
      {adding ? (
        <AssetEditor
          geometry={geometry}
          onClose={() => setAdding(false)}
          onSaved={() => {
            refresh();
            setMessage("Asset saved. Exposure rules recalculated.");
          }}
        />
      ) : null}
    </div>
  );
}
