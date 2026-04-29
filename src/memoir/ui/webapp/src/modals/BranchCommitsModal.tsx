import { useEffect, useRef, useState } from "react";
import { api, MemoirApiError } from "../api/client";
import type { BranchMergePreviewResponse } from "../api/types";
import { useStore } from "../state/storeSlice";
import { useUI } from "../state/uiSlice";
import "../drawers/DrawerPanels.css";
import "./BranchCommitsModal.css";

/**
 * "Memories on <branch> · not yet on <default>" modal — opened by clicking
 * the ↑ ahead pill on a branch row in SyncBranchesModal.
 *
 * Renders the same flat-by-key view that the merge confirmation panel
 * shows: just the add/update operations ``promote_branch`` would carry,
 * with BEFORE/AFTER content. No per-commit grouping (intermediate values
 * don't reach main, so showing them was misleading); no deletions
 * (``promote_branch`` is add/update-only).
 */
export default function BranchCommitsModal() {
  const branch = useUI((s) => s.branchCommitsTarget);
  const close = useUI((s) => s.closeBranchCommits);
  const storePath = useStore((s) => s.storePath);
  const data = useStore((s) => s.data);
  const refreshStore = useStore((s) => s.refresh);
  const defaultBranch = data?.branches.find((b) => b === "main") ?? data?.current_branch ?? "main";
  const currentBranch = data?.current_branch ?? null;

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previousActive = useRef<HTMLElement | null>(null);

  const [preview, setPreview] = useState<BranchMergePreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Bumped after each successful revert so the preview effect re-fetches.
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!branch || !storePath) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPreview(null);
    api
      .branchMergePreview(storePath, defaultBranch, branch)
      .then((res) => {
        if (cancelled) return;
        setPreview(res);
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
  }, [branch, storePath, defaultBranch, refreshKey]);

  const onReverted = () => {
    setRefreshKey((k) => k + 1);
    void refreshStore();
  };

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

  const totalChanges = preview
    ? preview.added.length + preview.modified.length
    : 0;

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
              Memories on <code>{branch}</code>
            </h2>
            <p className="branchcommits-subtitle">
              not yet on <code>{defaultBranch}</code>
              {preview && totalChanges > 0 && (
                <>
                  {" · "}
                  <span className="diff-stat added">+{preview.added.length}</span>{" "}
                  <span className="diff-stat modified">~{preview.modified.length}</span>
                </>
              )}
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
          {loading && <p className="drawer-empty-hint">Loading preview…</p>}
          {error && <p className="drawer-error">Failed: {error}</p>}
          {preview && totalChanges === 0 && (
            <p className="drawer-empty-hint">
              No default-namespace memories on <code>{branch}</code> differ from{" "}
              <code>{defaultBranch}</code>. Nothing would merge.
            </p>
          )}
          {preview && totalChanges > 0 && storePath && (
            <ul className="diff-cards">
              {preview.added.map((item) => (
                <ChangeCard
                  key={`add-${item.path}`}
                  type="added"
                  path={item.path}
                  newContent={item.new_content}
                  storePath={storePath}
                  viewedBranch={branch}
                  currentBranch={currentBranch}
                  onReverted={onReverted}
                />
              ))}
              {preview.modified.map((item) => (
                <ChangeCard
                  key={`mod-${item.path}`}
                  type="modified"
                  path={item.path}
                  oldContent={item.old_content}
                  newContent={item.new_content}
                  storePath={storePath}
                  viewedBranch={branch}
                  currentBranch={currentBranch}
                  onReverted={onReverted}
                />
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

interface ChangeCardProps {
  type: "added" | "modified";
  path: string;
  oldContent?: string;
  newContent: string;
  storePath: string;
  viewedBranch: string;
  currentBranch: string | null;
  onReverted: () => void;
}

function ChangeCard({
  type,
  path,
  oldContent,
  newContent,
  storePath,
  viewedBranch,
  currentBranch,
  onReverted,
}: ChangeCardProps) {
  const symbol = type === "added" ? "+" : "~";
  // Revert mutates the store's HEAD branch. Only enable when the user is
  // already on the branch they're viewing — cross-branch writes would
  // require server-side checkout/restore, which v1 doesn't do.
  const canRevert = currentBranch === viewedBranch;
  const [confirmState, setConfirmState] = useState<"idle" | "confirm" | "loading">(
    "idle",
  );
  const [error, setError] = useState<string | null>(null);

  // Auto-revert the confirmation prompt after 10s of inaction so the user
  // doesn't accidentally confirm a stale intent later.
  useEffect(() => {
    if (confirmState !== "confirm") return;
    const t = window.setTimeout(() => setConfirmState("idle"), 10_000);
    return () => window.clearTimeout(t);
  }, [confirmState]);

  const onRevertClick = async () => {
    if (confirmState === "idle") {
      setConfirmState("confirm");
      return;
    }
    if (confirmState !== "confirm") return;
    setConfirmState("loading");
    setError(null);
    try {
      if (type === "added") {
        // Reverting an add = delete the key.
        await api.forget(storePath, path, "default");
      } else if (oldContent != null) {
        // Reverting a modify = restore the BEFORE content.
        await api.updateMemory(storePath, path, oldContent, {
          namespace: "default",
          editSource: "manual",
        });
      } else {
        throw new Error("Cannot revert: no previous content available");
      }
      onReverted();
    } catch (err) {
      setError(err instanceof MemoirApiError ? err.message : String(err));
      setConfirmState("idle");
    }
  };

  const revertLabel =
    confirmState === "loading"
      ? "Reverting…"
      : confirmState === "confirm"
        ? "Confirm revert"
        : "Revert";
  const revertTitle = !canRevert
    ? `Switch to ${viewedBranch} to revert (currently on ${currentBranch ?? "unknown"})`
    : confirmState === "confirm"
      ? type === "added"
        ? `Click again to delete ${path} from ${viewedBranch}`
        : `Click again to restore the BEFORE content of ${path}`
      : `Revert this ${type} on ${viewedBranch}`;

  return (
    <li className={`diff-card type-${type}`}>
      <header className="diff-card-header">
        <span className="diff-card-sym" aria-hidden="true">
          {symbol}
        </span>
        <code className="diff-card-path">{path}</code>
        <span className={`diff-card-tag tag-${type}`}>{type.toUpperCase()}</span>
        <button
          type="button"
          className={`diff-card-revert${confirmState === "confirm" ? " is-confirm" : ""}`}
          disabled={!canRevert || confirmState === "loading"}
          onClick={onRevertClick}
          title={revertTitle}
        >
          {revertLabel}
        </button>
      </header>
      {type === "modified" && oldContent && (
        <div className="diff-card-section">
          <span className="diff-card-label">BEFORE:</span>
          <div className="diff-card-block before">{oldContent}</div>
        </div>
      )}
      {newContent && (
        <div className="diff-card-section">
          <span className="diff-card-label">AFTER:</span>
          <div className="diff-card-block after">{newContent}</div>
        </div>
      )}
      {error && <div className="diff-card-revert-error">Revert failed: {error}</div>}
    </li>
  );
}
