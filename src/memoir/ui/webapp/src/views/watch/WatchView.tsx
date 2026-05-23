import { useEffect, useMemo, useState } from "react";
import {
  api,
  MemoirApiError,
  type WatchListResponse,
  type WatchSearchResponse,
  type WatchStatsResponse,
} from "../../api/client";
import { useStore } from "../../state/storeSlice";
import "./WatchView.css";

/** Format an ISO-ish timestamp as a local date+time. */
function formatTime(s: string | null | undefined): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return s;
  }
}

export default function WatchView() {
  const storePath = useStore((s) => s.storePath);
  const connected = useStore((s) => s.status === "connected");

  const [listData, setListData] = useState<WatchListResponse | null>(null);
  const [statsData, setStatsData] = useState<WatchStatsResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [query, setQuery] = useState("");
  const [k, setK] = useState(5);
  const [searchData, setSearchData] = useState<WatchSearchResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  // The namespace toggle on the global filter bar isn't shown on this
  // view (we ship one bar per view). Keep it local — most users use the
  // default namespace.
  const namespace = "default";

  useEffect(() => {
    let cancelled = false;
    if (!storePath || !connected) {
      setListData(null);
      setStatsData(null);
      return;
    }
    setLoading(true);
    setLoadError(null);
    Promise.all([
      api.watchList(storePath),
      api.watchStats(storePath, namespace),
    ])
      .then(([list, stats]) => {
        if (cancelled) return;
        setListData(list);
        setStatsData(stats);
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg =
          err instanceof MemoirApiError ? err.message : String(err);
        setLoadError(msg);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [storePath, connected]);

  const sortedEntries = useMemo(() => {
    if (!listData?.entries) return [];
    return [...listData.entries].sort((a, b) =>
      a.path.localeCompare(b.path),
    );
  }, [listData]);

  const onSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!storePath || !query.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const res = await api.watchSearch(storePath, query.trim(), {
        namespace,
        k: Math.max(1, Math.min(k, 100)),
      });
      setSearchData(res);
    } catch (err: unknown) {
      const msg =
        err instanceof MemoirApiError ? err.message : String(err);
      setSearchError(msg);
      setSearchData(null);
    } finally {
      setSearching(false);
    }
  };

  if (!connected) {
    return (
      <div className="watch-view">
        <p className="watch-empty">Connect to a store to view watched paths.</p>
      </div>
    );
  }

  return (
    <div className="watch-view">
      <section className="watch-section">
        <header className="watch-section-header">
          <h2>Watched paths</h2>
          {listData && (
            <span className="watch-count">{listData.count} registered</span>
          )}
        </header>
        {loading && <p className="watch-loading">Loading…</p>}
        {loadError && <p className="watch-error">{loadError}</p>}
        {!loading && !loadError && sortedEntries.length === 0 && (
          <p className="watch-empty">
            No paths registered. Run{" "}
            <code>memoir watch add &lt;path&gt;</code> to start indexing.
          </p>
        )}
        {sortedEntries.length > 0 && (
          <table className="watch-table">
            <thead>
              <tr>
                <th>Path</th>
                <th>Kind</th>
                <th>Namespace</th>
                <th className="num">Indexed</th>
                <th>Last scan</th>
                <th>Added</th>
              </tr>
            </thead>
            <tbody>
              {sortedEntries.map((e) => (
                <tr key={e.path}>
                  <td className="watch-path" title={e.path}>
                    {e.path}
                  </td>
                  <td>{e.kind}</td>
                  <td>{e.namespace}</td>
                  <td className="num">{e.indexed_count}</td>
                  <td>{formatTime(e.last_scan)}</td>
                  <td>{formatTime(e.added_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="watch-section">
        <header className="watch-section-header">
          <h2>Proximity index stats</h2>
          <span className="watch-count">namespace: {namespace}</span>
        </header>
        {statsData && !statsData.available && (
          <p className="watch-empty">
            Vector index unavailable: {statsData.reason ?? "feature disabled"}.
          </p>
        )}
        {statsData && statsData.available && (
          <dl className="watch-stats">
            <div>
              <dt>Index</dt>
              <dd>{statsData.index_name ?? "—"}</dd>
            </div>
            <div>
              <dt>Documents</dt>
              <dd>{statsData.doc_count ?? 0}</dd>
            </div>
            <div>
              <dt>Chunks</dt>
              <dd>{statsData.chunk_count ?? 0}</dd>
            </div>
            <div>
              <dt>In sync</dt>
              <dd>{statsData.in_sync ? "yes" : "no"}</dd>
            </div>
            <div>
              <dt>Orphans</dt>
              <dd>{statsData.orphans ?? 0}</dd>
            </div>
            <div>
              <dt>Missing</dt>
              <dd>{statsData.missing ?? 0}</dd>
            </div>
            {statsData.note && (
              <div className="watch-stats-note">
                <dt>Note</dt>
                <dd>{statsData.note}</dd>
              </div>
            )}
          </dl>
        )}
      </section>

      <section className="watch-section">
        <header className="watch-section-header">
          <h2>Vector search</h2>
        </header>
        <form className="watch-search-form" onSubmit={onSearch}>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Query (e.g. 'rust ownership')"
            className="watch-search-input"
          />
          <label className="watch-k-label">
            k
            <input
              type="number"
              min={1}
              max={100}
              value={k}
              onChange={(e) => setK(Number(e.target.value) || 1)}
              className="watch-k-input"
            />
          </label>
          <button
            type="submit"
            disabled={searching || !query.trim()}
            className="watch-search-button"
          >
            {searching ? "Searching…" : "Search"}
          </button>
        </form>
        {searchError && <p className="watch-error">{searchError}</p>}
        {searchData && searchData.hits.length === 0 && (
          <p className="watch-empty">No matches for "{searchData.query}".</p>
        )}
        {searchData && searchData.hits.length > 0 && (
          <>
            <p className="watch-search-summary">
              {searchData.hits.length} hit
              {searchData.hits.length === 1 ? "" : "s"} in{" "}
              {searchData.timing_ms.toFixed(1)} ms (lower score = closer)
            </p>
            <ol className="watch-hits">
              {searchData.hits.map((hit, i) => (
                <li key={`${hit.key}-${i}`} className="watch-hit">
                  <div className="watch-hit-head">
                    <span className="watch-hit-key">{hit.key}</span>
                    <span className="watch-hit-score">
                      score: {hit.score.toFixed(4)}
                    </span>
                  </div>
                  {hit.source?.abs_path && (
                    <div className="watch-hit-source" title={hit.source.abs_path}>
                      {hit.source.abs_path}
                    </div>
                  )}
                  <div className="watch-hit-content">
                    {hit.content.length > 400
                      ? hit.content.slice(0, 400) + "…"
                      : hit.content}
                  </div>
                </li>
              ))}
            </ol>
          </>
        )}
      </section>
    </div>
  );
}
