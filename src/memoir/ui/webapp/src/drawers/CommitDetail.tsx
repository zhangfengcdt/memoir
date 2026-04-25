import { useEffect, useState } from "react";
import { api, MemoirApiError } from "../api/client";
import type { Change, Commit, CommitDiff, RangeDiffResponse } from "../api/types";
import { useStore } from "../state/storeSlice";
import { relativeTime } from "../lib/time";
import "./DrawerPanels.css";

interface CommitDetailProps {
  commit: Commit;
}

/**
 * Memory Store Diff panel — shows the changes introduced by ``commit``
 * against its first parent. Mirrors v1's "Memory Store Diff" popup:
 * comparison header, +/~/− stat chips, then per-change cards with the
 * BEFORE / AFTER content.
 *
 * For root commits (no parent), there's nothing to diff against — we
 * fall back to a "this is the initial commit" message and still show
 * the metadata so the panel isn't empty.
 */
export default function CommitDetail({ commit }: CommitDetailProps) {
  const storePath = useStore((s) => s.storePath);
  const parentHash = commit.parents[0]; // first parent — canonical line of history
  const [data, setData] = useState<RangeDiffResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!storePath || !parentHash) {
      setData(null);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .rangeDiff(storePath, parentHash, commit.hash)
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
  }, [storePath, parentHash, commit.hash]);

  // The range-diff response has one entry per commit in the from..to
  // range; we always asked for parent..commit, so the entry we want is
  // the one matching ``commit.hash``.
  const diff: CommitDiff | undefined = data?.commits.find(
    (c) => c.hash === commit.hash,
  );

  return (
    <div className="drawer-panel commit-detail">
      <section className="drawer-panel-section">
        <div className="diff-comparing">
          {parentHash ? (
            <code>
              Comparing {parentHash.slice(0, 7)} <span className="diff-arrow">→</span>{" "}
              {commit.short_hash}
            </code>
          ) : (
            <code>Initial commit · {commit.short_hash} (no parent to compare)</code>
          )}
        </div>
        <p className="commit-tagline" title={commit.message}>
          <code className="commit-tagline-hash">{commit.short_hash}</code>
          <span className="commit-tagline-msg">{commit.message}</span>
          <span className="commit-tagline-meta">
            {commit.author} · {relativeTime(commit.timestamp)}
          </span>
        </p>
      </section>

      {loading && (
        <section className="drawer-panel-section">
          <p className="drawer-empty-hint">Computing diff…</p>
        </section>
      )}
      {error && (
        <section className="drawer-panel-section">
          <p className="drawer-error">Failed to compute diff: {error}</p>
        </section>
      )}

      {!parentHash && !loading && (
        <section className="drawer-panel-section">
          <p className="drawer-empty-hint">
            This is the root commit — no prior state to diff against.
          </p>
        </section>
      )}

      {diff && (
        <>
          <section className="drawer-panel-section">
            <div className="diff-stats">
              <span className="diff-stat-pill added">
                +{diff.stats.added} addition{diff.stats.added === 1 ? "" : "s"}
              </span>
              <span className="diff-stat-pill modified">
                ~{diff.stats.modified} modification
                {diff.stats.modified === 1 ? "" : "s"}
              </span>
              <span className="diff-stat-pill deleted">
                −{diff.stats.deleted} deletion{diff.stats.deleted === 1 ? "" : "s"}
              </span>
            </div>
          </section>

          <section className="drawer-panel-section">
            {diff.changes.length === 0 ? (
              <p className="drawer-empty-hint">
                No key-level changes — this commit may only carry metadata.
              </p>
            ) : (
              <ul className="diff-cards">
                {diff.changes.map((change, i) => (
                  <ChangeCard key={`${change.path}-${i}`} change={change} />
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function ChangeCard({ change }: { change: Change }) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    const text = change.new_content ?? change.old_content ?? "";
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable — silent */
    }
  };

  const symbol = change.type === "added" ? "+" : change.type === "deleted" ? "−" : "~";

  return (
    <li className={`diff-card type-${change.type}`}>
      <header className="diff-card-header">
        <span className="diff-card-sym" aria-hidden="true">
          {symbol}
        </span>
        <code className="diff-card-path">{change.path}</code>
        <span className={`diff-card-tag tag-${change.type}`}>{change.type.toUpperCase()}</span>
        <button
          type="button"
          className="diff-card-copy"
          onClick={onCopy}
          title="Copy content"
          aria-label="Copy content"
        >
          {copied ? "✓ Copied" : "Copy"}
        </button>
      </header>

      {(change.type === "modified" || change.type === "deleted") && change.old_content && (
        <div className="diff-card-section">
          <span className="diff-card-label">BEFORE:</span>
          <div className="diff-card-block before">{change.old_content}</div>
        </div>
      )}

      {(change.type === "modified" || change.type === "added") && change.new_content && (
        <div className="diff-card-section">
          <span className="diff-card-label">AFTER:</span>
          <div className="diff-card-block after">{change.new_content}</div>
        </div>
      )}
    </li>
  );
}
