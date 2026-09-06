import { useEffect, useRef, useState } from "react";
import { RefreshCw } from "lucide-react";
import { post, timeAgo, useResource } from "../api";
import { Button, StatusMessage } from "./ui";
interface SyncStatus {
  configured: boolean;
  interval_seconds: number;
  last_success: string | null;
  last_error: string | null;
  result: {
    created: number;
    updated: number;
    unlocated: number;
    missing: number;
  } | null;
  job: { id: string; status: string; error: string | null } | null;
}
export default function NetBoxSync({ onChange }: { onChange: () => void }) {
  const { data, error, refresh } = useResource<SyncStatus>(
    "/integrations/netbox",
  );
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const previous = useRef<string | null>(null);
  useEffect(() => {
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    if (data?.last_success && data.last_success !== previous.current) {
      previous.current = data.last_success;
      onChange();
    }
  }, [data?.last_success, onChange]);
  const active = data?.job && ["pending", "running"].includes(data.job.status);
  return (
    <section
      className="panel padded netbox-sync"
      aria-label="NetBox site synchronization"
    >
      <div className="section-toolbar">
        <div>
          <h2>NetBox sites</h2>
          <p className="muted">
            Keep saved locations aligned with your network inventory. Exposure
            rules stay local.
          </p>
        </div>
        <Button
          busy={busy}
          disabled={!data?.configured || !!active}
          onClick={async () => {
            setBusy(true);
            setFailure("");
            try {
              await post("/integrations/netbox/sync");
              refresh();
            } catch (e) {
              setFailure((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <RefreshCw size={16} />
          {active ? "Sync queued or running" : "Sync from NetBox"}
        </Button>
      </div>
      {data?.configured ? (
        <>
          <p>
            Last successful sync: <strong>{timeAgo(data.last_success)}</strong>{" "}
            ·{" "}
            {data.interval_seconds
              ? `Automatic sync every ${Math.max(60, data.interval_seconds) / 60} minutes`
              : "Manual sync only"}
          </p>
          {data.result ? (
            <p>
              {data.result.created} added · {data.result.updated} refreshed ·{" "}
              {data.result.unlocated} without usable coordinates ·{" "}
              {data.result.missing} no longer returned by NetBox
            </p>
          ) : null}
          <p className="muted">
            Missing or unlocated imports stay listed, but do not appear on the
            map or generate exposure alerts. A failed sync keeps the last
            successful snapshot.
          </p>
        </>
      ) : (
        <p className="muted">
          Configure WATCH_NETBOX_URL and WATCH_NETBOX_TOKEN in your deployment’s
          .env, then recreate the API and worker. Use a read-only token with
          site access. Sites need latitude and longitude.
        </p>
      )}
      <StatusMessage error>
        {failure || error || data?.last_error}
      </StatusMessage>
    </section>
  );
}
