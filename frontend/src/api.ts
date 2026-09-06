import { useCallback, useEffect, useState } from "react";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch("/api/v1" + path, {
    ...init,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...init.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body?.error;
    throw new ApiError(
      detail?.fields
        ?.map(
          (e: { field: string; message: string }) => `${e.field}: ${e.message}`,
        )
        .join("; ") ||
        detail?.message ||
        "Service unavailable. Try again.",
      response.status,
    );
  }
  return response.json();
}
export const post = <T>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export function useResource<T>(path: string | null, revision = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  const refresh = useCallback(() => setReload((n) => n + 1), []);
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    api<T>(path, { signal: controller.signal })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [path, revision, reload]);
  return { data, error, loading, refresh };
}
export function timeAgo(date: string | null) {
  if (!date) return "Never collected";
  const minutes = Math.max(
    0,
    Math.floor((Date.now() - new Date(date).getTime()) / 60000),
  );
  return minutes < 1
    ? "Just now"
    : minutes < 60
      ? `${minutes}m ago`
      : minutes < 1440
        ? `${Math.floor(minutes / 60)}h ago`
        : `${Math.floor(minutes / 1440)}d ago`;
}
export const severityLabel = (value: number) =>
  ["Unknown", "Low", "Moderate", "High", "Extreme"][value] || "Unknown";
