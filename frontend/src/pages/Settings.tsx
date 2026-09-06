import { useState } from "react";
import { KeyRound, ExternalLink, Webhook as WebhookIcon } from "lucide-react";
import { api, post, useResource } from "../api";
import type {
  Credential,
  Job,
  List,
  Settings as SettingsType,
  Webhook,
} from "../types";
import {
  Button,
  Confirm,
  Field,
  Secret,
  StatusMessage,
} from "../components/ui";
export default function Settings({ config }: { config: SettingsType }) {
  const [revision, setRevision] = useState(0);
  const tokens = useResource<List<Credential>>("/tokens", revision);
  const hooks = useResource<List<Webhook>>("/webhooks", revision);
  const jobs = useResource<List<Job>>("/jobs", revision);
  const [name, setName] = useState("");
  const [scope, setScope] = useState("read");
  const [token, setToken] = useState("");
  const [hookName, setHookName] = useState("");
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [remove, setRemove] = useState<{
    path: string;
    name: string;
    verb: string;
  }>();
  const [job, setJob] = useState<Job>();
  return (
    <>
      <div className="settings-grid">
        <section className="panel padded">
          <h2>
            <KeyRound size={18} />
            API access
          </h2>
          <p className="muted">
            Scoped credentials for your mapping tools. Tokens are shown once.
          </p>
          <form
            noValidate
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              try {
                const r = await post<{ token: string }>("/tokens", {
                  name,
                  scopes: scope === "write" ? ["read", "write"] : [scope],
                  days: 90,
                });
                setToken(r.token);
                setRevision((n) => n + 1);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Field
              label="Token name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Company map integration"
            />
            <label className="field">
              Permissions
              <select value={scope} onChange={(e) => setScope(e.target.value)}>
                <option value="read">Read events and GIS layers</option>
                <option value="write">Read and manage assets/alerts</option>
                <option value="admin">Full administrator access</option>
              </select>
            </label>
            <Button type="submit" variant="primary" busy={busy}>
              Create token
            </Button>
          </form>
          {token ? (
            <Secret
              label="New API token — save it now"
              value={token}
              readOnly
            />
          ) : null}
          <ul className="settings-list">
            {tokens.data?.items.map((t) => (
              <li key={t.id}>
                <div>
                  {t.name}
                  <small>
                    {t.scopes.join(", ")} ·{" "}
                    {t.revoked_at
                      ? "Revoked"
                      : new Date(t.expires_at).toLocaleDateString()}
                  </small>
                </div>
                <Button
                  disabled={!!t.revoked_at}
                  onClick={() =>
                    setRemove({
                      path: "/tokens/" + t.id,
                      name: t.name,
                      verb: "Revoke token",
                    })
                  }
                >
                  Revoke
                </Button>
              </li>
            ))}
          </ul>
          <a href="/api/docs" target="_blank" rel="noreferrer">
            API documentation <ExternalLink size={14} />
          </a>
          <br />
          <a
            href="/gis/collections/events?f=json"
            target="_blank"
            rel="noreferrer"
          >
            OGC feature collection <ExternalLink size={14} />
          </a>
        </section>
        <section className="panel padded">
          <h2>
            <WebhookIcon size={18} />
            Alert delivery
          </h2>
          <p className="muted">
            Signed webhooks deliver exposure alerts to your systems. Private
            destinations need an explicit hostname allowlist.
          </p>
          <form
            noValidate
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              try {
                const r = await post<{ secret: string }>("/webhooks", {
                  name: hookName,
                  url,
                });
                setSecret(r.secret);
                setRevision((n) => n + 1);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Field
              label="Subscription name"
              value={hookName}
              onChange={(e) => setHookName(e.target.value)}
            />
            <Field
              label="Destination URL"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <Button type="submit" variant="primary" busy={busy}>
              Add webhook
            </Button>
          </form>
          {secret ? (
            <Secret
              label="Signing secret — save it now"
              value={secret}
              readOnly
            />
          ) : null}
          <ul className="settings-list">
            {hooks.data?.items.map((h) => (
              <li key={h.id}>
                <div>
                  {h.name}
                  <small>{h.enabled ? "Enabled" : "Disabled"}</small>
                </div>
                <Button
                  disabled={!h.enabled}
                  onClick={() =>
                    setRemove({
                      path: "/webhooks/" + h.id,
                      name: h.name,
                      verb: "Disable webhook",
                    })
                  }
                >
                  Disable
                </Button>
              </li>
            ))}
          </ul>
        </section>
      </div>
      <StatusMessage error>
        {error || tokens.error || hooks.error || jobs.error}
      </StatusMessage>
      <section className="panel padded integration-status">
        <h2>Local services</h2>
        <p>
          Local AI:{" "}
          <strong>{config.ai_enabled ? "Configured" : "Not connected"}</strong>{" "}
          · SpiderFoot:{" "}
          <strong>
            {config.spiderfoot_enabled ? "Configured" : "Not connected"}
          </strong>
        </p>
        <p className="muted">
          Raw evidence: {config.raw_retention_days} days · Normalized history:{" "}
          {config.retention_days} days. Configure endpoints, basemap, and
          retention in .env. Restart services after changes.
        </p>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <h2>Jobs and deliveries</h2>
          <Button onClick={() => setRevision((n) => n + 1)}>
            Refresh jobs
          </Button>
        </div>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Kind</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {jobs.data?.items.map((j) => (
                <tr key={j.id}>
                  <td>{j.kind}</td>
                  <td>{j.status}</td>
                  <td>{j.attempts}</td>
                  <td>
                    <Button
                      onClick={async () => {
                        try {
                          setJob(await api<Job>("/jobs/" + j.id));
                        } catch (e) {
                          setError((e as Error).message);
                        }
                      }}
                    >
                      Inspect job
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {job ? (
          <div className="padded">
            <h3>
              {job.kind} — {job.status}
            </h3>
            <pre className="job-result">
              {JSON.stringify(job.result || { error: job.error }, null, 2)}
            </pre>
          </div>
        ) : null}
      </section>
      {remove ? (
        <Confirm
          title={remove.verb}
          onClose={() => setRemove(undefined)}
          onConfirm={async () => {
            await api(remove.path, { method: "DELETE" });
            setRevision((n) => n + 1);
          }}
        >
          {remove.verb} “{remove.name}”? Existing consumers will lose this
          access.
        </Confirm>
      ) : null}
    </>
  );
}
