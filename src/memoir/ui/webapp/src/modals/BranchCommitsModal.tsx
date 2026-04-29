import { useEffect, useRef, useState } from "react";
import { api, MemoirApiError } from "../api/client";
import type { Change, CommitDiff, RangeDiffResponse } from "../api/types";
import { useStore } from "../state/storeSlice";
import { useUI } from "../state/uiSlice";
import { relativeTime } from "../lib/time";
import "../drawers/DrawerPanels.css";
import "./BranchCommitsModal.css";

/**
 * "Commits on <branch> · not yet on <default>" modal — opened by
 * clicking the ↑N-ahead pill on a branch row in SyncBranchesModal.
 *
 * Reuses /api/commit-range-diff (default..branch) and the same change-card
 * styles as the CommitDetail drawer so the visual language stays
 * consistent across diff views.
 */
export default function BranchCommitsModal() {
  const branch = useUI((s) => s.branchCommitsTarget);
  const close = useUI((s) => s.closeBranchCommits);
  const storePath = useStore((s) => s.storePath);
  const data = useStore((s) => s.data);
  const defaultBranch = data?.branches.find((b) => b === "main") ?? data?.current_branch ?? "main";

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previousActive = useRef<HTMLElement | null>(null);

  const [diff, setDiff] = useState<RangeDiffResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!branch || !storePath) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDiff(null);
    api
      .rangeDiff(storePath, defaultBranch, branch)
      .then((res) => {
        if (cancelled) return;
        setDiff(res);
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
  }, [branch, storePath, defaultBranch]);

  // Focus management.
  useEffect(() => {
    if (!branch) return;
    previousActive.current = document.activeElement as HTMLElement | null;
    requestAnimationFrame(() => dialogRef.current?.focus());
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previousActive.current?.focus?.();
    };
  }, [branch, close]);

  if (!branch) return null;

  // The range-diff response orders commits old → new (chronological).
  // Reverse so the most recent commit is at the top — matches v1's layout.
  const commits = diff ? [...diff.commits].reverse() : [];

  return (
    <div
      className="branchcommits-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        ref={dialogRef}
        className="branchcommits-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="branchcommits-title"
        tabIndex={-1}
      >
        <header className="branchcommits-header">
          <div>
            <h2 id="branchcommits-title" className="branchcommits-title">
              Commits on <code>{branch}</code>
            </h2>
            <p className="branchcommits-subtitle">
              not yet on <code>{defaultBranch}</code>
            </p>
          </div>
          <button
            type="button"
            className="branchcommits-close"
            onClick={close}
            aria-label="Close branch commits"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </header>

        <div className="branchcommits-body">
          {loading && <p className="drawer-empty-hint">Loading commits…</p>}
          {error && <p className="drawer-error">Failed: {error}</p>}
          {diff && commits.length === 0 && (
            <p className="drawer-empty-hint">
              No commits on this branch are missing from <code>{defaultBranch}</code>.
            </p>
          )}
          {commits.length > 0 && (
            <ul className="branchcommits-list">
              {commits.map((c) => (
                <CommitSection key={c.hash} commit={c} />
              ))}
            </ul>
          )}
        </div>

        <footer className="branchcommits-footer">
          Each section is one commit. Only additions and updates are shown — deletions don't sync to main.
        </footer>
      </div>
    </div>
  );
}

function CommitSection({ commit }: { commit: CommitDiff }) {
  // sync-branch is add/update only — deletions never reach main, so hide them
  // from this preview to keep it aligned with what an actual merge would carry.
  const syncableChanges = commit.changes.filter((c) => c.type !== "deleted");
  return (
    <li className="branchcommits-section">
      <header className="branchcommits-commit-head">
        <code className="branchcommits-commit-hash">{commit.short_hash}</code>
        <span className="branchcommits-commit-msg" title={commit.message}>
          {commit.message}
        </span>
        <div className="branchcommits-commit-stats">
          <span className="diff-stat added">+{commit.stats.added}</span>
          <span className="diff-stat modified">~{commit.stats.modified}</span>
        </div>
      </header>
      <p className="branchcommits-commit-meta">
        {commit.author} · {relativeTime(commit.timestamp)}
      </p>
      {syncableChanges.length > 0 ? (
        <ul className="diff-cards">
          {syncableChanges.map((change, i) => (
            <ChangeCard key={`${change.path}-${i}`} change={change} />
          ))}
        </ul>
      ) : (
        <p className="drawer-empty-hint">
          No additions or updates — this commit only deletes keys, which won't
          merge to main.
        </p>
      )}
    </li>
  );
}

function ChangeCard({ change }: { change: Change }) {
  const symbol = change.type === "added" ? "+" : change.type === "deleted" ? "−" : "~";
  return (
    <li className={`diff-card type-${change.type}`}>
      <header className="diff-card-header">
        <span className="diff-card-sym" aria-hidden="true">
          {symbol}
        </span>
        <code className="diff-card-path">{change.path}</code>
        <span className={`diff-card-tag tag-${change.type}`}>{change.type.toUpperCase()}</span>
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
