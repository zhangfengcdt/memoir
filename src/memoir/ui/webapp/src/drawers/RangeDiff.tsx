import { useEffect, useState } from "react";
import { api, MemoirApiError } from "../api/client";
import type { Change, CommitDiff, RangeDiffResponse } from "../api/types";
import { useStore } from "../state/storeSlice";
import { relativeTime } from "../lib/time";
import "./DrawerPanels.css";

interface RangeDiffProps {
  fromHash: string;
  toHash: string;
}

export default function RangeDiff({ fromHash, toHash }: RangeDiffProps) {
  const storePath = useStore((s) => s.storePath);
  const [data, setData] = useState<RangeDiffResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!storePath) return;
    setLoading(true);
    setError(null);
    api
      .rangeDiff(storePath, fromHash, toHash)
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
  }, [storePath, fromHash, toHash]);

  if (loading) {
    return (
      <div className="drawer-panel range-diff">
        <PanelHeader fromHash={fromHash} toHash={toHash} />
        <p className="drawer-empty-hint">Computing diff…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="drawer-panel range-diff">
        <PanelHeader fromHash={fromHash} toHash={toHash} />
        <p className="drawer-error">Failed to compute diff: {error}</p>
      </div>
    );
  }

  if (!data) return null;

  const totalAdded = data.commits.reduce((n, c) => n + c.stats.added, 0);
  const totalModified = data.commits.reduce((n, c) => n + c.stats.modified, 0);
  const totalDeleted = data.commits.reduce((n, c) => n + c.stats.deleted, 0);

  return (
    <div className="drawer-panel range-diff">
      <PanelHeader fromHash={fromHash} toHash={toHash} />

      <section className="drawer-panel-section">
        <span className="eyebrow">Summary</span>
        <div className="diff-summary">
          <span>{data.commits.length} commits</span>
          <span className="diff-sep" aria-hidden="true">
            ·
          </span>
          <span className="diff-stat added">+{totalAdded}</span>
          <span className="diff-stat modified">~{totalModified}</span>
          <span className="diff-stat deleted">−{totalDeleted}</span>
        </div>
      </section>

      {data.commits.length === 0 ? (
        <p className="drawer-empty-hint">
          No commits between these refs. They may be the same, or ``from`` may be
          an ancestor of ``to``.
        </p>
      ) : (
        <section className="drawer-panel-section">
          <span className="eyebrow">Commits in range</span>
          <ol className="diff-commit-list">
            {data.commits.map((c) => (
              <CommitDiffItem key={c.hash} commit={c} />
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

function PanelHeader({ fromHash, toHash }: { fromHash: string; toHash: string }) {
  return (
    <header className="drawer-panel-header">
      <span className="eyebrow">Range diff</span>
      <h3 className="drawer-panel-title">
        <code>{fromHash.slice(0, 7)}</code>
        <span className="diff-arrow" aria-hidden="true">
          →
        </span>
        <code>{toHash.slice(0, 7)}</code>
      </h3>
    </header>
  );
}

function CommitDiffItem({ commit }: { commit: CommitDiff }) {
  return (
    <li className="diff-commit">
      <div className="diff-commit-head">
        <code className="diff-commit-hash">{commit.short_hash}</code>
        <span className="diff-commit-message">{commit.message}</span>
      </div>
      <div className="diff-commit-meta">
        <span>{commit.author}</span>
        <span className="diff-sep" aria-hidden="true">
          ·
        </span>
        <span>{relativeTime(commit.timestamp)}</span>
        <span className="diff-sep" aria-hidden="true">
          ·
        </span>
        <span className="diff-stat added">+{commit.stats.added}</span>
        <span className="diff-stat modified">~{commit.stats.modified}</span>
        <span className="diff-stat deleted">−{commit.stats.deleted}</span>
      </div>
      {commit.changes.length > 0 && (
        <ul className="diff-change-list">
          {commit.changes.map((change, i) => (
            <ChangeRow key={`${change.path}-${i}`} change={change} />
          ))}
        </ul>
      )}
    </li>
  );
}

function ChangeRow({ change }: { change: Change }) {
  const symbol = change.type === "added" ? "+" : change.type === "deleted" ? "−" : "~";
  return (
    <li className={`diff-change type-${change.type}`}>
      <span className="diff-change-sym" aria-hidden="true">
        {symbol}
      </span>
      <code className="diff-change-path">{change.path}</code>
      {change.type === "modified" && change.old_content && change.new_content && (
        <div className="diff-change-inline">
          <span className="diff-inline-old">{truncate(change.old_content)}</span>
          <span aria-hidden="true"> → </span>
          <span className="diff-inline-new">{truncate(change.new_content)}</span>
        </div>
      )}
      {change.type === "added" && change.new_content && (
        <div className="diff-change-inline">
          <span className="diff-inline-new">{truncate(change.new_content)}</span>
        </div>
      )}
      {change.type === "deleted" && change.old_content && (
        <div className="diff-change-inline">
          <span className="diff-inline-old">{truncate(change.old_content)}</span>
        </div>
      )}
    </li>
  );
}

function truncate(s: string, max = 100): string {
  const oneLine = s.split("\n")[0];
  return oneLine.length > max ? oneLine.slice(0, max) + "…" : oneLine;
}
