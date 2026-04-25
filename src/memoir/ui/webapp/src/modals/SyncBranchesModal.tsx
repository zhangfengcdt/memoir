import { useCallback, useEffect, useRef, useState } from "react";
import { api, MemoirApiError } from "../api/client";
import type { BranchStatus, BranchesStatusResponse } from "../api/types";
import { useStore } from "../state/storeSlice";
import { useUI } from "../state/uiSlice";
import { useConfig } from "../state/configSlice";
import { relativeTimeFromISO } from "../lib/time";
import "./SyncBranchesModal.css";

/**
 * Sync Branches modal — v1 parity.
 *
 * Lists every local branch with its divergence vs the default branch
 * ("ahead" count or "synced"). Lets the user merge any non-default
 * branch into main, or delete a non-current branch. The current branch
 * gets a "CURRENT" pill and an accent border so it's obvious where you
 * are.
 *
 * "Merge into main" calls /api/sync-branches with the default branch
 * as ``target``. memoir is local-first today; nothing is pushed to a
 * remote — the label matches v1 but the action is a local merge.
 */
export default function SyncBranchesModal() {
  const open = useUI((s) => s.branchesOpen);
  const close = useUI((s) => s.closeBranches);
  const storePath = useStore((s) => s.storePath);
  const writable = useConfig((s) => s.writable);

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previousActive = useRef<HTMLElement | null>(null);

  const [data, setData] = useState<BranchesStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Branch name currently performing an action (push/delete) — used to
   * disable both buttons on that row while the request is in flight. */
  const [busyBranch, setBusyBranch] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!storePath) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.branchesStatus(storePath);
      setData(res);
    } catch (err) {
      setError(err instanceof MemoirApiError ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [storePath]);

  useEffect(() => {
    if (!open) return;
    void refresh();
  }, [open, refresh]);

  // Focus management.
  useEffect(() => {
    if (!open) return;
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
  }, [open, close]);

  if (!open) return null;

  const onMerge = async (branch: BranchStatus) => {
    if (!storePath || !data) return;
    setBusyBranch(branch.name);
    setError(null);
    try {
      const res = await api.syncBranch(storePath, branch.name, data.default);
      if (res.conflicts && res.conflicts.length > 0) {
        setError(
          `Merge conflict on ${branch.name}: ${res.conflicts.length} key(s) need manual resolution.`,
        );
      }
      // Always refresh — even on partial failure the ahead count may have moved.
      await refresh();
      // Also refresh the parent store so the rest of the UI sees the
      // new commits in main.
      await useStore.getState().refresh();
    } catch (err) {
      setError(err instanceof MemoirApiError ? err.message : String(err));
    } finally {
      setBusyBranch(null);
    }
  };

  const onDelete = async (branch: BranchStatus) => {
    if (!storePath) return;
    // Confirm before destructive action.
    const ok = window.confirm(
      `Delete branch "${branch.name}"? This is permanent and cannot be undone.`,
    );
    if (!ok) return;
    setBusyBranch(branch.name);
    setError(null);
    try {
      await api.deleteBranch(storePath, branch.name);
      await refresh();
      await useStore.getState().refresh();
    } catch (err) {
      setError(err instanceof MemoirApiError ? err.message : String(err));
    } finally {
      setBusyBranch(null);
    }
  };

  // Order: current branch first (so the user sees their own context at
  // the top), then default if not current, then everything else by name.
  const branches = (data?.branches ?? []).slice().sort((a, b) => {
    if (a.is_current !== b.is_current) return a.is_current ? -1 : 1;
    if (a.is_default !== b.is_default) return a.is_default ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  const aheadCount = branches.filter((b) => !b.is_default && b.ahead > 0).length;

  return (
    <div
      className="sync-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        ref={dialogRef}
        className="sync-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sync-title"
        tabIndex={-1}
      >
        <header className="sync-header">
          <div>
            <h2 id="sync-title" className="sync-title">
              Sync Branches
            </h2>
            {data && (
              <p className="sync-subtitle">
                <span>Default: </span>
                <code>{data.default}</code>
                <span className="sync-sep" aria-hidden="true">
                  ·
                </span>
                <span>On: </span>
                <code>{data.current}</code>
              </p>
            )}
          </div>
          <button
            type="button"
            className="sync-close"
            onClick={close}
            aria-label="Close branches"
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

        {loading && !data && (
          <p className="sync-empty">Loading branches…</p>
        )}
        {error && (
          <p className="sync-error" role="alert">
            {error}
          </p>
        )}

        {data && (
          <ul className="sync-list">
            {branches.map((branch) => (
              <BranchRow
                key={branch.name}
                branch={branch}
                defaultBranch={data.default}
                disabled={!writable || busyBranch !== null}
                isBusy={busyBranch === branch.name}
                onMerge={onMerge}
                onDelete={onDelete}
              />
            ))}
          </ul>
        )}

        <footer className="sync-footer">
          <span>
            Counts are git commits between branches — one memory may land as
            multiple commits.
          </span>
          {data && (
            <span>
              {aheadCount} branch{aheadCount === 1 ? "" : "es"} with unmerged commits
            </span>
          )}
        </footer>
      </div>
    </div>
  );
}

interface BranchRowProps {
  branch: BranchStatus;
  defaultBranch: string;
  disabled: boolean;
  isBusy: boolean;
  onMerge: (b: BranchStatus) => void;
  onDelete: (b: BranchStatus) => void;
}

function BranchRow({
  branch,
  defaultBranch,
  disabled,
  isBusy,
  onMerge,
  onDelete,
}: BranchRowProps) {
  const isDefault = branch.is_default;
  const isCurrent = branch.is_current;
  const synced = branch.synced || branch.ahead === 0;
  const openBranchCommits = useUI((s) => s.openBranchCommits);

  // Merge into main is only meaningful for non-default branches that
  // actually have commits to contribute. Delete is forbidden for the
  // current branch (you can't delete the branch you're standing on).
  const canMerge = !isDefault && !synced;
  const canDelete = !isDefault && !isCurrent;

  return (
    <li className={`sync-row${isCurrent ? " current" : ""}`}>
      <div className="sync-row-main">
        <code className="sync-branch-name">{branch.name}</code>
        {isCurrent && <span className="sync-pill current">CURRENT</span>}
        {isDefault && !isCurrent && <span className="sync-pill default">DEFAULT</span>}
        <p className="sync-row-meta">
          last commit {relativeTimeFromISO(branch.last_commit_date)}
        </p>
      </div>
      <div className="sync-row-actions">
        {synced ? (
          <span className="sync-status synced">✓ synced</span>
        ) : (
          // Clicking the ahead pill opens the per-commit diff modal so
          // users can see exactly what's about to be merged.
          <button
            type="button"
            className="sync-status ahead clickable"
            onClick={() => openBranchCommits(branch.name)}
            title={`See the ${branch.ahead} commit${branch.ahead === 1 ? "" : "s"} not yet on ${defaultBranch}`}
          >
            ↑ {branch.ahead} ahead
          </button>
        )}
        <button
          type="button"
          className="sync-btn merge"
          onClick={() => onMerge(branch)}
          disabled={!canMerge || disabled}
          title={
            !canMerge
              ? isDefault
                ? "This is the default branch"
                : "Already merged into the default branch"
              : `Merge ${branch.name} into ${defaultBranch}`
          }
        >
          {isBusy ? "Merging…" : `Merge into ${defaultBranch}`}
        </button>
        <button
          type="button"
          className="sync-btn delete"
          onClick={() => onDelete(branch)}
          disabled={!canDelete || disabled}
          title={
            !canDelete
              ? isCurrent
                ? "Can't delete the current branch"
                : "Can't delete the default branch"
              : `Delete ${branch.name}`
          }
        >
          {isBusy ? "…" : "Delete"}
        </button>
      </div>
    </li>
  );
}
