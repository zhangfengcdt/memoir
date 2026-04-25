import { useEffect, useMemo, useState } from "react";
import { api, MemoirApiError } from "../../api/client";
import type { LocationResponse } from "../../api/types";
import { useStore } from "../../state/storeSlice";
import "./PlacesView.css";

export default function PlacesView() {
  const storePath = useStore((s) => s.storePath);
  const connected = useStore((s) => s.status === "connected");
  const [data, setData] = useState<LocationResponse | null>(null);
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
      .locations(storePath)
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

  const places = useMemo(
    () => (data ? Object.entries(data.location_data) : []),
    [data],
  );

  if (!connected) return null;
  if (loading && !data) return <div className="places-empty">Loading places…</div>;
  if (error) return <div className="places-empty places-error">Failed: {error}</div>;

  if (!data || places.length === 0) {
    return (
      <div className="places-empty">
        <span className="eyebrow">Places</span>
        <h3 className="places-empty-title">No places captured yet</h3>
        <p>
          Memories captured with location metadata appear here as cards. A future
          phase pins them on a map; for now this view is a quick lightweight roll-up.
        </p>
      </div>
    );
  }

  return (
    <div className="places-wrapper">
      <div className="places-header">
        <span className="eyebrow">Places</span>
        <span className="places-count">
          {places.length} place{places.length === 1 ? "" : "s"}
        </span>
      </div>

      {data.summary && (
        <div className="places-summary card">
          <span className="eyebrow">Summary</span>
          <p>{data.summary}</p>
        </div>
      )}

      <ul className="places-grid">
        {places.map(([slug, place]) => (
          <li key={slug} className="place-card">
            <header className="place-card-header">
              <span className="place-icon" aria-hidden="true">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                  <circle cx="12" cy="10" r="3" />
                </svg>
              </span>
              <h4 className="place-name">{place.name}</h4>
              <code className="place-slug" title={slug}>
                {slug}
              </code>
            </header>
            <p className="place-content">{place.content}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
