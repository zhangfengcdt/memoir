import { useEffect, useMemo, useRef, useState } from "react";
import { api, MemoirApiError } from "../api/client";
import type { BranchMergePreviewResponse } from "../api/types";
import { useStore } from "../state/storeSlice";
import { useUI } from "../state/uiSlice";
import "../drawers/DrawerPanels.css";
import "./BranchCommitsModal.css";
import "./BringOverMemoriesModal.css";

/**
 * Second half of the History view's time-travel flow: after branching
 * from a historical commit, offer to bring forward specific memories
 * from the branch the user was working on. Picking none leaves the new
 * branch exactly as it was at that commit — no extra commit is made.
 */
export default function BringOverMemoriesModal() {
  const target = useUI((s) => s.bringOverTarget);
  const close = useUI((s) => s.closeBringOver);
  const storePath = useStore((s) => s.storePath);
  const refresh = useStore((s) => s.refresh);

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previousActive = useRef<HTMLElement | null>(null);

  const [preview, setPreview] = useState<BranchMergePreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    if (!target || !storePath) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPreview(null);
    // NB: `branchMergePreview(path, fromRef, toRef)`'s params are the
    // *target* branch (receiving) then the *source* branch (being
    // inspected) — inverted from `syncBranch`'s (source, target). We want
    // "what's on target.source that isn't yet on target.target", so
    // fromRef = target.target, toRef = target.source. See the doc comment
    // on `api.branchMergePreview` in api/client.ts.
    api
      .branchMergePreview(storePath, target.target, target.source)
      .then((res) => {
        if (cancelled) return;
        setPreview(res);
        setSelected(
          new Set([
            ...res.added.map((a) => a.path),
            ...res.modified.map((m) => m.path),
          ]),
        );
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
  }, [target, storePath]);

  useEffect(() => {
    if (!target) return;
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
  }, [target, close]);

  const allPaths = useMemo(
    () =>
      preview
        ? [...preview.added.map((a) => a.path), ...preview.modified.map((m) => m.path)]
        : [],
    [preview],
  );

  if (!target || !storePath) return null;

  const toggle = (path: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  const onApply = async () => {
    if (selected.size === 0) {
      close();
      return;
    }
    setApplying(true);
    setError(null);
    try {
      const excludedKeys = allPaths.filter((p) => !selected.has(p));
      await api.syncBranch(storePath, target.source, target.target, {
        confirm: true,
        excludedKeys,
      });
      await refresh();
      close();
    } catch (err) {
      setError(err instanceof MemoirApiError ? err.message : String(err));
      setApplying(false);
    }
  };

  const totalChanges = preview ? preview.added.length + preview.modified.length : 0;

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
        aria-labelledby="bring-over-title"
        tabIndex={-1}
      >
        <header className="branchcommits-header">
          <div>
            <h2 id="bring-over-title" className="branchcommits-title">
              Bring memories to <code>{target.target}</code>
            </h2>
            <p className="branchcommits-subtitle">
              from <code>{target.source}</code>
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
            aria-label="Close"
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
              <code>{target.target}</code> already has everything from{" "}
              <code>{target.source}</code>. Nothing to bring over.
            </p>
          )}
          {preview && totalChanges > 0 && (
            <ul className="diff-cards bring-over-list">
              {preview.added.map((item) => (
                <li key={`add-${item.path}`} className="diff-card type-added">
                  <label className="bring-over-row">
                    <input
                      type="checkbox"
                      checked={selected.has(item.path)}
                      onChange={() => toggle(item.path)}
                    />
                    <span className="diff-card-sym" aria-hidden="true">
                      +
                    </span>
                    <code className="diff-card-path">{item.path}</code>
                    <span className="diff-card-tag tag-added">ADDED</span>
                  </label>
                </li>
              ))}
              {preview.modified.map((item) => (
                <li key={`mod-${item.path}`} className="diff-card type-modified">
                  <label className="bring-over-row">
                    <input
                      type="checkbox"
                      checked={selected.has(item.path)}
                      onChange={() => toggle(item.path)}
                    />
                    <span className="diff-card-sym" aria-hidden="true">
                      ~
                    </span>
                    <code className="diff-card-path">{item.path}</code>
                    <span className="diff-card-tag tag-modified">MODIFIED</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </div>

        <footer className="branch-from-commit-footer">
          <button type="button" className="btn btn-ghost btn-sm" onClick={close} disabled={applying}>
            {totalChanges === 0 ? "Close" : "Skip — leave branch as-is"}
          </button>
          {preview && totalChanges > 0 && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={onApply}
              disabled={applying || loading}
            >
              {applying
                ? "Applying…"
                : selected.size === 0
                  ? "Bring over nothing"
                  : `Bring over ${selected.size} selected`}
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
