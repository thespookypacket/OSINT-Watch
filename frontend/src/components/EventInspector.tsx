import { useEffect, useState } from "react";
import { ExternalLink, X, Sparkles } from "lucide-react";
import { api, post, severityLabel, useResource } from "../api";
import { categories, type EventDetail, type Job } from "../types";
import { Button, StatusMessage } from "./ui";
export default function EventInspector({
  id,
  aiEnabled,
  onClose,
}: {
  id: string;
  aiEnabled: boolean;
  onClose: () => void;
}) {
  const { data, error, loading } = useResource<EventDetail>("/events/" + id);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => {
    setJob(null);
    setMessage("");
  }, [id]);
  useEffect(() => {
    if (!job || ["complete", "failed"].includes(job.status)) return;
    const timer = setInterval(() => {
      api<Job>("/jobs/" + job.id)
        .then(setJob)
        .catch((e) => setMessage(e.message));
    }, 3000);
    return () => clearInterval(timer);
  }, [job]);
  const p = data?.event.properties;
  return (
    <aside className="inspector panel" aria-label="Event details">
      <div className="panel-heading">
        <h2>Event details</h2>
        <Button
          variant="ghost"
          aria-label="Close event details"
          onClick={onClose}
        >
          <X size={18} />
        </Button>
      </div>
      <StatusMessage error>{error || message}</StatusMessage>
      {loading && !p ? <p className="padded">Loading evidence…</p> : null}
      {p ? (
        <div className="inspector-body">
          <span
            className="category-label"
            style={{ color: categories[p.category].color }}
          >
            {categories[p.category].label}
          </span>
          <h2>{p.title}</h2>
          <div className="tags">
            <span className={"severity severity-" + p.severity}>
              {severityLabel(p.severity)}
            </span>
            <span className="tag">{p.status}</span>
            <span className="tag">{p.confidence}</span>
          </div>
          <dl>
            <dt>Source</dt>
            <dd>{p.attribution}</dd>
            <dt>Source severity</dt>
            <dd>{p.source_severity}</dd>
            <dt>Location precision</dt>
            <dd>{p.precision}</dd>
            <dt>Occurred</dt>
            <dd>
              {new Date(p.occurred_at).toLocaleString(undefined, {
                timeZoneName: "short",
              })}
            </dd>
            <dt>Source updated</dt>
            <dd>
              {new Date(p.updated_at).toLocaleString(undefined, {
                timeZoneName: "short",
              })}
            </dd>
          </dl>
          {p.description ? (
            <p className="description">{p.description}</p>
          ) : null}
          {/^https?:\/\//i.test(p.evidence_url) ? (
            <a
              className="evidence-link"
              href={p.evidence_url}
              target="_blank"
              rel="noreferrer"
            >
              Open source evidence <ExternalLink size={14} />
            </a>
          ) : null}
          <h3>Asset exposure</h3>
          {data.exposures.length ? (
            data.exposures.map((a) => <p key={a.id}>{a.reason}</p>)
          ) : (
            <p className="muted">
              No matching asset rules. Unlocated events cannot be evaluated
              spatially.
            </p>
          )}
          <h3>Revision history</h3>
          <ol className="revision-list">
            {data.revisions.map((r) => (
              <li key={r.seq}>
                {r.operation} · {new Date(r.created_at).toLocaleString()}
              </li>
            ))}
          </ol>
          {data.related.length ? (
            <>
              <h3>Possible related reports</h3>
              {data.related.map((r) => (
                <p key={r.id}>
                  {r.title}
                  <small>{r.reason}</small>
                </p>
              ))}
            </>
          ) : null}
          <Button
            busy={busy}
            disabled={!aiEnabled}
            onClick={async () => {
              setBusy(true);
              try {
                const result = await post<{ id: string }>("/summaries", {
                  event_ids: [id],
                });
                setJob({
                  id: result.id,
                  kind: "summary",
                  status: "pending",
                  attempts: 0,
                  error: null,
                });
              } catch (e) {
                setMessage((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Sparkles size={16} />
            Summarize evidence locally
          </Button>
          {!aiEnabled ? (
            <small className="muted">
              Local AI is optional and currently disconnected.
            </small>
          ) : null}
          {job ? (
            <StatusMessage error={job.status === "failed"}>
              {job.result?.summary ||
                job.error ||
                "Summary queued. Monitoring continues while the local model works."}
              {job.result?.evidence_ids ? (
                <small>References: {job.result.evidence_ids.join(", ")}</small>
              ) : null}
            </StatusMessage>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}
