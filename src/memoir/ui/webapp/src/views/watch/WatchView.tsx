import { Fragment, useEffect, useMemo, useState } from "react";
import {
  api,
  MemoirApiError,
  type WatchFile,
  type WatchListResponse,
  type WatchSearchResponse,
} from "../../api/client";
import { useStore } from "../../state/storeSlice";
import "./WatchView.css";

/** Format a byte count compactly. */
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** Render ``abs_path`` relative to the watched root if it lives inside. */
function relativeTo(absPath: string, root: string): string {
  if (absPath === root) return absPath;
  const prefix = root.endsWith("/") ? root : root + "/";
  return absPath.startsWith(prefix) ? absPath.slice(prefix.length) : absPath;
}

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
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const [query, setQuery] = useState("");
  const [k, setK] = useState(5);
  const [searchData, setSearchData] = useState<WatchSearchResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searching, setSearching] = useState(false);

  // Per-watched-path expansion state for the "Watched paths" table.
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [filesCache, setFilesCache] = useState<
    Record<string, { loading: boolean; files: WatchFile[]; error: string | null }>
  >({});

  // Add-file form state.
  const [addPath, setAddPath] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // Per-path remove state. Tracks paths currently being removed so the
  // row's Remove button can show a "removing…" label without blocking
  // the rest of the table.
  const [removing, setRemoving] = useState<Set<string>>(new Set());

  // Monotonic refresh trigger. Incrementing this re-fires the load
  // effect, which re-fetches /api/watch/list. Handlers bump it after a
  // mutating action (add/scan/scan-all/remove) so the table updates
  // without the user manually reloading.
  const [refreshTick, setRefreshTick] = useState(0);
  const refresh = () => setRefreshTick((n) => n + 1);

  const toggleExpand = (entryPath: string, kind: string) => {
    if (kind !== "folder") return;
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(entryPath)) {
        next.delete(entryPath);
        return next;
      }
      next.add(entryPath);
      return next;
    });
    if (!filesCache[entryPath] && storePath) {
      setFilesCache((prev) => ({
        ...prev,
        [entryPath]: { loading: true, files: [], error: null },
      }));
      api
        .watchFiles(storePath, entryPath)
        .then((res) => {
          setFilesCache((prev) => ({
            ...prev,
            [entryPath]: {
              loading: false,
              files: res.files ?? [],
              error: res.error,
            },
          }));
        })
        .catch((err: unknown) => {
          const msg = err instanceof MemoirApiError ? err.message : String(err);
          setFilesCache((prev) => ({
            ...prev,
            [entryPath]: { loading: false, files: [], error: msg },
          }));
        });
    }
  };

  // Watched memories live under their own "watch" namespace so they don't
  // mix with `memoir remember` content under "default".
  const namespace = "watch";

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    if (!storePath || !connected) {
      setListData(null);
      return;
    }

    // Poll while any row is indexing. The interval is short while there's
    // an in-flight scan (2s) and stops once everything's settled — the
    // user can refresh manually by switching views to re-trigger this
    // effect.
    let firstRun = true;
    const tick = () => {
      if (firstRun) {
        setLoading(true);
        firstRun = false;
      }
      setLoadError(null);
      api
        .watchList(storePath)
        .then((list) => {
          if (cancelled) return;
          setListData(list);
          setLoading(false);
          const anyIndexing = (list.entries ?? []).some((e) => e.indexing);
          if (anyIndexing) {
            timer = setTimeout(tick, 2000);
          }
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          const msg =
            err instanceof MemoirApiError ? err.message : String(err);
          setLoadError(msg);
          setLoading(false);
        });
    };
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
    // Bumping ``refreshTick`` re-runs this effect so add/scan/remove
    // handlers can request an immediate re-fetch.
  }, [storePath, connected, refreshTick]);

  const sortedEntries = useMemo(() => {
    if (!listData?.entries) return [];
    return [...listData.entries].sort((a, b) =>
      a.path.localeCompare(b.path),
    );
  }, [listData]);

  const onScanAll = async () => {
    if (!storePath) return;
    try {
      const res = await api.watchScanAll(storePath);
      if (res.scheduled === 0) {
        setAddError("No watched files to scan.");
        return;
      }
      // Re-fetch so the polling loop picks up the indexing badges as
      // the server walks the registry.
      refresh();
    } catch (err: unknown) {
      const msg =
        err instanceof MemoirApiError ? err.message : String(err);
      setAddError(`scan all failed: ${msg}`);
    }
  };

  const onScanRow = async (e: React.MouseEvent, entryPath: string) => {
    e.stopPropagation();
    if (!storePath) return;
    try {
      await api.watchScanPath(storePath, entryPath);
      refresh();
    } catch (err: unknown) {
      const msg =
        err instanceof MemoirApiError ? err.message : String(err);
      setAddError(`scan failed: ${msg}`);
    }
  };

  const onRemoveRow = async (e: React.MouseEvent, entryPath: string) => {
    e.stopPropagation();
    if (!storePath) return;
    const ok = window.confirm(
      `Remove this watched file and delete all of its indexed memories?\n\n${entryPath}\n\nThis cannot be undone (data + vector entries are purged).`,
    );
    if (!ok) return;
    setRemoving((prev) => {
      const next = new Set(prev);
      next.add(entryPath);
      return next;
    });
    try {
      await api.watchRemovePath(storePath, entryPath);
      // Optimistic local prune so the row vanishes immediately — don't
      // wait for the network round-trip + re-render path. The refresh()
      // below also fires a fresh /api/watch/list to reconcile.
      setListData((prev) =>
        prev
          ? {
              ...prev,
              entries: prev.entries.filter((row) => row.path !== entryPath),
              count: Math.max(0, (prev.count ?? 0) - 1),
            }
          : prev,
      );
      refresh();
    } catch (err: unknown) {
      const msg =
        err instanceof MemoirApiError ? err.message : String(err);
      setAddError(`remove failed: ${msg}`);
    } finally {
      setRemoving((prev) => {
        const next = new Set(prev);
        next.delete(entryPath);
        return next;
      });
    }
  };

  const onAddFile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!storePath || !addPath.trim()) return;
    setAdding(true);
    setAddError(null);
    try {
      await api.watchAddPath(storePath, addPath.trim());
      setAddPath("");
      // Re-fetch so the new row shows up immediately with the indexing
      // badge; subsequent polls keep it updated until the server-side
      // scan completes.
      refresh();
    } catch (err: unknown) {
      const msg =
        err instanceof MemoirApiError ? err.message : String(err);
      setAddError(msg);
    } finally {
      setAdding(false);
    }
  };

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
        <form className="watch-add-form" onSubmit={onAddFile}>
          <input
            type="text"
            value={addPath}
            onChange={(e) => setAddPath(e.target.value)}
            placeholder="Absolute path to a file (e.g. /Users/you/Desktop/notes.md)"
            className="watch-add-input"
            disabled={adding}
          />
          <button
            type="submit"
            disabled={adding || !addPath.trim()}
            className="btn watch-add-button"
            title="Kick off indexing for this file. Returns immediately; the row shows 'indexing…' until the server finishes."
          >
            {adding ? "Adding…" : "Add file"}
          </button>
          <button
            type="button"
            onClick={onScanAll}
            disabled={
              !listData ||
              listData.entries.length === 0 ||
              (listData.entries ?? []).some((e) => e.indexing)
            }
            className="btn watch-scan-all-button"
            title="Re-scan every registered file, one at a time. Each row lights up 'indexing…' as the server gets to it."
          >
            Scan all
          </button>
        </form>
        {addError && <p className="watch-error">{addError}</p>}
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
                <th className="watch-caret-col"></th>
                <th>Path</th>
                <th>Kind</th>
                <th>Namespace</th>
                <th className="num">Indexed</th>
                <th>Last scan</th>
                <th>Added</th>
                <th className="watch-actions-col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedEntries.map((e) => {
                const isFolder = e.kind === "folder";
                const isOpen = expanded.has(e.path);
                const cache = filesCache[e.path];
                return (
                  <Fragment key={e.path}>
                    <tr
                      className={
                        isFolder ? "watch-row watch-row-folder" : "watch-row"
                      }
                      onClick={() => toggleExpand(e.path, e.kind)}
                      style={{ cursor: isFolder ? "pointer" : "default" }}
                    >
                      <td className="watch-caret-col">
                        {isFolder && (
                          <span
                            className={`watch-caret ${isOpen ? "open" : ""}`}
                            aria-label={isOpen ? "Collapse" : "Expand"}
                          >
                            ▶
                          </span>
                        )}
                      </td>
                      <td className="watch-path" title={e.path}>
                        {e.path}
                        {e.indexing && (
                          <span
                            className="watch-badge watch-badge-indexing"
                            title="Server is indexing this file in the background."
                          >
                            indexing…
                          </span>
                        )}
                        {!e.indexing && e.indexing_error && (
                          <span
                            className="watch-badge watch-badge-error"
                            title={e.indexing_error}
                          >
                            failed
                          </span>
                        )}
                      </td>
                      <td>{e.kind}</td>
                      <td>{e.namespace}</td>
                      <td className="num">{e.indexed_count}</td>
                      <td>{formatTime(e.last_scan)}</td>
                      <td>{formatTime(e.added_at)}</td>
                      <td className="watch-actions-col">
                        <button
                          type="button"
                          className="btn btn-sm watch-row-action"
                          onClick={(ev) => onScanRow(ev, e.path)}
                          disabled={e.indexing || removing.has(e.path)}
                          title="Re-index this file. Picks up content changes; same indexing pipeline as the initial add."
                        >
                          Scan
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm watch-row-action watch-row-action-danger"
                          onClick={(ev) => onRemoveRow(ev, e.path)}
                          disabled={e.indexing || removing.has(e.path)}
                          title="Unregister this file and purge every raw.<file>.* key from KV + vector. Cannot be undone."
                        >
                          {removing.has(e.path) ? "Removing…" : "Remove"}
                        </button>
                      </td>
                    </tr>
                    {isFolder && isOpen && (
                      <tr className="watch-files-row">
                        <td></td>
                        <td colSpan={7} className="watch-files-cell">
                          {cache?.loading && (
                            <p className="watch-loading">Loading files…</p>
                          )}
                          {cache?.error && (
                            <p className="watch-error">{cache.error}</p>
                          )}
                          {cache && !cache.loading && !cache.error && (
                            cache.files.length === 0 ? (
                              <p className="watch-empty">
                                No indexed files under this path yet.
                              </p>
                            ) : (
                              <table className="watch-files-table">
                                <thead>
                                  <tr>
                                    <th>File</th>
                                    <th className="num">Size</th>
                                    <th className="num">Summary chars</th>
                                    <th>Indexed</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {cache.files.map((f) => (
                                    <tr key={f.abs_path}>
                                      <td
                                        className="watch-file-path"
                                        title={f.abs_path}
                                      >
                                        {relativeTo(f.abs_path, e.path)}
                                      </td>
                                      <td className="num">
                                        {formatSize(f.size)}
                                      </td>
                                      <td className="num">{f.summary_chars}</td>
                                      <td>{formatTime(f.indexed_at)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
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
