import { useEffect, useMemo, useState } from "react";
import { api, MemoirApiError } from "../../api/client";
import type { TimelineResponse } from "../../api/types";
import { useStore } from "../../state/storeSlice";
import "./TimelineView.css";

/** ``YYYYMMDD`` → ``YYYY-MM-DD`` for display. */
function formatDateKey(key: string): string {
  if (key.length !== 8) return key;
  return `${key.slice(0, 4)}-${key.slice(4, 6)}-${key.slice(6, 8)}`;
}

/** ``YYYYMMDD`` → human readable: "Apr 24, 2026 — Friday". */
function describeDate(key: string): string {
  if (key.length !== 8) return key;
  const y = Number(key.slice(0, 4));
  const m = Number(key.slice(4, 6));
  const d = Number(key.slice(6, 8));
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function TimelineView() {
  const storePath = useStore((s) => s.storePath);
  const connected = useStore((s) => s.status === "connected");
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!storePath || !connected) {
      setData(null);
      return;
    }
    setLoading(true);
    setError(null);
    api
      .timeline(storePath)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof MemoirApiError ? err.message : String(err));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [storePath, connected]);

  const sortedEntries = useMemo(() => {
    if (!data) return [];
    // YYYYMMDD sorts naturally as a string. Newest first.
    return Object.entries(data.timeline_data).sort(([a], [b]) =>
      b.localeCompare(a),
    );
  }, [data]);

  if (!connected) return null;
  if (loading && !data) return <div className="timeline-empty">Loading timeline…</div>;
  if (error) {
    return <div className="timeline-empty timeline-error">Failed: {error}</div>;
  }

  if (!data || sortedEntries.length === 0) {
    return (
      <div className="timeline-empty">
        <span className="eyebrow">Timeline</span>
        <h3 className="timeline-empty-title">No timeline events yet</h3>
        <p>
          Capture memories tagged with a date (or via{" "}
          <code>memoir remember</code> with timeline metadata) and they'll appear here
          chronologically. Run <code>/refresh</code> after seeding.
        </p>
      </div>
    );
  }

  return (
    <div className="timeline-wrapper">
      <div className="timeline-header">
        <span className="eyebrow">Timeline</span>
        <span className="timeline-count">
          {sortedEntries.length} day{sortedEntries.length === 1 ? "" : "s"}
        </span>
      </div>

      {data.summary && (
        <div className="timeline-summary card">
          <span className="eyebrow">Summary</span>
          <p>{data.summary}</p>
        </div>
      )}

      <ol className="timeline-list">
        {sortedEntries.map(([dateKey, content]) => (
          <li key={dateKey} className="timeline-entry">
            <div className="timeline-entry-rail" aria-hidden="true">
              <span className="timeline-entry-dot" />
            </div>
            <article className="timeline-entry-card">
              <header className="timeline-entry-header">
                <code className="timeline-entry-date">{formatDateKey(dateKey)}</code>
                <span className="timeline-entry-desc">{describeDate(dateKey)}</span>
              </header>
              <p className="timeline-entry-content">{content}</p>
            </article>
          </li>
        ))}
      </ol>
    </div>
  );
}
