import { useEffect, useMemo, useState, MouseEvent } from "react";
import { api, MemoirApiError } from "../../api/client";
import type { Commit } from "../../api/types";
import { useStore } from "../../state/storeSlice";
import { useSelection } from "../../state/selectionSlice";
import { useUI } from "../../state/uiSlice";

/**
 * Namespace filtering for the commits list requires per-commit
 * "namespaces touched" data the backend doesn't currently return on
 * ``/api/commits``. Until that lands, commits show in full and we
 * surface a small note in the header so users aren't surprised.
 */
import CommitRow from "./CommitRow";
import "./CommitList.css";

interface CommitListProps {
  limit?: number;
}

export default function CommitList({ limit = 50 }: CommitListProps) {
  const storePath = useStore((s) => s.storePath);
  const connected = useStore((s) => s.status === "connected");
  const currentBranch = useStore((s) => s.data?.current_branch ?? null);

  const [commits, setCommits] = useState<Commit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const primary = useSelection((s) => s.primary);
  const selectedHashes = useSelection((s) => s.selectedHashes);
  const namespaceFilter = useUI((s) => s.selectedNamespace);

  useEffect(() => {
    let cancelled = false;
    if (!storePath || !connected) {
      setCommits(null);
      return;
    }
    setLoading(true);
    setError(null);
    api
      .commits(storePath, { limit })
      .then((res) => {
        if (cancelled) return;
        setCommits(res.commits);
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
  }, [storePath, connected, limit]);

  const orderedHashes = useMemo(
    () => (commits ? commits.map((c) => c.hash) : []),
    [commits],
  );

  const onRowClick = (hash: string, event: MouseEvent<HTMLLIElement>) => {
    const sel = useSelection.getState();
    if (event.shiftKey) {
      sel.selectRange(hash, orderedHashes);
    } else if (event.metaKey || event.ctrlKey) {
      sel.toggle(hash);
    } else {
      sel.pick(hash);
      // Plain click also opens the commit in the drawer for quick inspection.
      const commit = commits?.find((c) => c.hash === hash);
      if (commit) {
        useUI.getState().pushPanel({ kind: "commit-detail", commit });
      }
    }
  };

  const onKeyNav = (hash: string, key: "ArrowUp" | "ArrowDown" | "Enter") => {
    if (key === "Enter") return;
    const idx = orderedHashes.indexOf(hash);
    if (idx < 0) return;
    const nextIdx = key === "ArrowUp" ? Math.max(0, idx - 1) : Math.min(orderedHashes.length - 1, idx + 1);
    useSelection.getState().pick(orderedHashes[nextIdx]);
    // Move focus to the new row.
    const next = document.querySelector<HTMLLIElement>(
      `li.commit-row[data-hash="${orderedHashes[nextIdx]}"]`,
    );
    next?.focus();
  };

  if (!connected) {
    return null;
  }

  if (loading && commits === null) {
    return <div className="commit-list-empty">Loading commits…</div>;
  }

  if (error) {
    return (
      <div className="commit-list-empty commit-list-error">
        Failed to load commits: {error}
      </div>
    );
  }

  if (commits && commits.length === 0) {
    return (
      <div className="commit-list-empty">
        <p>No commits yet. Run <code>/remember</code> to capture something.</p>
      </div>
    );
  }

  if (!commits) return null;

  const selectedCount = selectedHashes.size;

  return (
    <div className="commit-list-wrapper">
      <div className="commit-list-header">
        <div className="commit-list-meta">
          <span>{commits.length} shown</span>
          {namespaceFilter && (
            <span
              className="chip"
              title="Namespace filter is applied to the Tree view; commits show all changes."
            >
              filter: {namespaceFilter}
            </span>
          )}
          {selectedCount > 1 && (
            <span className="chip accent">
              {selectedCount} selected — range-diff ready
            </span>
          )}
          {selectedCount === 1 && primary && (
            <span className="chip">selected: {primary.slice(0, 7)}</span>
          )}
        </div>
      </div>
      <ul className="commit-list" role="listbox" aria-label="Commit history">
        {commits.map((c, i) => (
          <CommitRow
            key={c.hash}
            commit={c}
            selected={selectedHashes.has(c.hash)}
            isPrimary={primary === c.hash}
            isFirst={i === 0}
            isLast={i === commits.length - 1}
            currentBranch={currentBranch}
            onClick={onRowClick}
            onKeyNav={onKeyNav}
          />
        ))}
      </ul>
    </div>
  );
}
