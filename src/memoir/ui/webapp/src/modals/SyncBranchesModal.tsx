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
  /** Branch whose row is currently showing the inline delete-confirm
   * panel. ``null`` = no confirm visible. v1 uses an inline panel
   * rather than ``window.confirm`` so the dialog is themed with the
   * rest of the modal and doesn't break flow. */
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null);

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

  // Step 1: clicking the row's Delete button reveals an inline confirm
  // panel (no native dialog). Step 2: clicking "Delete" inside the
  // panel actually fires the request.
  const onDeleteClick = (branch: BranchStatus) => {
    setConfirmingDelete((current) => (current === branch.name ? null : branch.name));
  };

  const onCancelDelete = () => setConfirmingDelete(null);

  const onConfirmDelete = async (branch: BranchStatus) => {
    if (!storePath) return;
    setConfirmingDelete(null);
    setBusyBranch(branch.name);
    setError(null);
    try {
      // ``force: true`` (the client default) — memoir's "merged" status
      // is tracked via a sync marker, not git ancestry, so a perfectly
      // sync'd branch can still look "not fully merged" to git.
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
                isConfirmingDelete={confirmingDelete === branch.name}
                onMerge={onMerge}
                onDeleteClick={onDeleteClick}
                onConfirmDelete={onConfirmDelete}
                onCancelDelete={onCancelDelete}
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
  isConfirmingDelete: boolean;
  onMerge: (b: BranchStatus) => void;
  onDeleteClick: (b: BranchStatus) => void;
  onConfirmDelete: (b: BranchStatus) => void;
  onCancelDelete: () => void;
}

function BranchRow({
  branch,
  defaultBranch,
  disabled,
  isBusy,
  isConfirmingDelete,
  onMerge,
  onDeleteClick,
  onConfirmDelete,
  onCancelDelete,
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
    <li className={`sync-row${isCurrent ? " current" : ""}${isConfirmingDelete ? " confirming" : ""}`}>
      <div className="sync-row-top">
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
            onClick={() => onDeleteClick(branch)}
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
      </div>

      {isConfirmingDelete && (
        <div className="sync-confirm" role="alertdialog" aria-label="Confirm delete">
          <div className="sync-confirm-text">
            <strong className="sync-confirm-title">
              Delete memoir branch <code>{branch.name}</code>?
            </strong>
            <p className="sync-confirm-hint">
              This removes the branch ref from this memoir store only. It does{" "}
              <strong>not</strong> touch your project's code branches.
            </p>
          </div>
          <div className="sync-confirm-actions">
            <button
              type="button"
              className="sync-btn"
              onClick={onCancelDelete}
              autoFocus
            >
              Cancel
            </button>
            <button
              type="button"
              className="sync-btn delete sync-confirm-yes"
              onClick={() => onConfirmDelete(branch)}
            >
              Delete
            </button>
          </div>
        </div>
      )}
    </li>
  );
}
