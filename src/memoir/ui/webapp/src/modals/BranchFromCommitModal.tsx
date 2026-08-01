import { useEffect, useRef, useState } from "react";
import { api, MemoirApiError } from "../api/client";
import { useStore } from "../state/storeSlice";
import { useUI } from "../state/uiSlice";
import "./BranchCommitsModal.css";
import "./BranchFromCommitModal.css";

/**
 * "Branch from this commit" — the first half of the History view's
 * time-travel flow. Reuses the exact recipe the `/time-travel` command
 * already ships (`api.checkout(path, commitHash, branchName)`, which
 * forks+switches atomically), just with a user-editable branch name
 * instead of the command's fixed `travel-<short>`.
 *
 * On success, immediately opens BringOverMemoriesModal so the user can
 * pick which memories from the branch they were on to carry forward —
 * the second half of the flow.
 */
export default function BranchFromCommitModal() {
  const target = useUI((s) => s.branchFromCommitTarget);
  const close = useUI((s) => s.closeBranchFromCommit);
  const storePath = useStore((s) => s.storePath);
  const refresh = useStore((s) => s.refresh);

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previousActive = useRef<HTMLElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (target) {
      setName(`time-travel-${target.commit.short_hash}`);
      setError(null);
      setBusy(false);
    }
  }, [target]);

  useEffect(() => {
    if (!target) return;
    previousActive.current = document.activeElement as HTMLElement | null;
    requestAnimationFrame(() => inputRef.current?.focus());
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
  }, [target, close]);

  if (!target || !storePath) return null;
  const { commit, sourceBranch } = target;

  const onConfirm = async () => {
    const branchName = name.trim();
    if (!branchName) {
      setError("Branch name is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.checkout(storePath, commit.hash, branchName);
      await refresh();
      close();
      useUI.getState().openBringOver(sourceBranch, branchName);
    } catch (err) {
      setError(err instanceof MemoirApiError ? err.message : String(err));
      setBusy(false);
    }
  };

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
        className="branchcommits-dialog branch-from-commit-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="branch-from-commit-title"
        tabIndex={-1}
      >
        <header className="branchcommits-header">
          <div>
            <h2 id="branch-from-commit-title" className="branchcommits-title">
              Branch from <code>{commit.short_hash}</code>
            </h2>
            <p className="branchcommits-subtitle">{commit.message}</p>
          </div>
          <button
            type="button"
            className="branchcommits-close"
            onClick={close}
            aria-label="Cancel"
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
          <label className="branch-from-commit-label" htmlFor="branch-from-commit-name">
            New branch name
          </label>
          <input
            id="branch-from-commit-name"
            ref={inputRef}
            className="branch-from-commit-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") onConfirm();
            }}
            spellCheck={false}
            disabled={busy}
          />
          <p className="drawer-empty-hint">
            Creates <code>{name || "…"}</code> rooted at {commit.short_hash} and switches to it.
            Afterward you can pick which memories from <code>{sourceBranch}</code> to bring
            forward.
          </p>
          {error && <p className="drawer-error">Failed: {error}</p>}
        </div>

        <footer className="branch-from-commit-footer">
          <button type="button" className="btn btn-ghost btn-sm" onClick={close} disabled={busy}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary btn-sm"
            onClick={onConfirm}
            disabled={busy || !name.trim()}
          >
            {busy ? "Creating…" : "Create & switch"}
          </button>
        </footer>
      </div>
    </div>
  );
}
