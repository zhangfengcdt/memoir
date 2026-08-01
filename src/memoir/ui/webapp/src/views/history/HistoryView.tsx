import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import { api, MemoirApiError } from "../../api/client";
import type { ChangeType, Commit, Memory } from "../../api/types";
import { useStore } from "../../state/storeSlice";
import { useUI } from "../../state/uiSlice";
import { useHistorySelection } from "../../state/historySelectionSlice";
import CommitRow from "../commits/CommitRow";
import CategoryTree from "./CategoryTree";
import { categoryOf } from "../../lib/category";
import "../commits/CommitList.css";
import "./HistoryView.css";

/**
 * Commit + branch timeline for visual time-travel: click a commit to see
 * what it changed (grouped/colored by taxonomy category), click a branch
 * chip to inspect that branch's history without checking it out, and
 * "Branch from here" to fork a new branch rooted at a historical commit
 * (see BranchFromCommitModal + BringOverMemoriesModal for the rest of
 * that flow).
 */
export default function HistoryView() {
  const storePath = useStore((s) => s.storePath);
  const connected = useStore((s) => s.status === "connected");
  const data = useStore((s) => s.data);
  const currentBranch = data?.current_branch ?? null;
  const branches = useMemo(() => data?.branches ?? [], [data]);
  const revision = useStore((s) => s.revision);

  // Branch whose commit history is being *viewed* — defaults to current,
  // but clicking another branch chip inspects its history without
  // checking it out (no write, just a different `/api/commits?branch=`).
  const [viewedBranch, setViewedBranch] = useState<string | null>(null);
  // Tracks the last `currentBranch` we saw, so we can tell "the checked-out
  // branch changed underneath the view we were already following" (e.g.
  // Branch-from-here's checkout, or the branch switcher) apart from "the
  // user deliberately picked a different branch chip to inspect". Only the
  // former should drag `viewedBranch` along.
  const lastCurrentBranch = useRef<string | null>(null);
  useEffect(() => {
    if (!currentBranch) return;
    if (viewedBranch === null || viewedBranch === lastCurrentBranch.current) {
      setViewedBranch(currentBranch);
    }
    lastCurrentBranch.current = currentBranch;
  }, [currentBranch, viewedBranch]);
  useEffect(() => {
    if (viewedBranch && branches.length > 0 && !branches.includes(viewedBranch)) {
      setViewedBranch(currentBranch);
    }
  }, [branches, viewedBranch, currentBranch]);

  const [commits, setCommits] = useState<Commit[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!storePath || !connected || !viewedBranch) {
      setCommits(null);
      return;
    }
    setLoading(true);
    setError(null);
    api
      .commits(storePath, { branch: viewedBranch, limit: 50 })
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
  }, [storePath, connected, viewedBranch, revision]);

  const orderedHashes = useMemo(
    () => (commits ? commits.map((c) => c.hash) : []),
    [commits],
  );

  const primary = useHistorySelection((s) => s.primary);
  const selectedHashes = useHistorySelection((s) => s.selectedHashes);

  const onRowClick = (hash: string, event: MouseEvent<HTMLLIElement>) => {
    const sel = useHistorySelection.getState();
    if (event.shiftKey) {
      sel.selectRange(hash, orderedHashes);
    } else if (event.metaKey || event.ctrlKey) {
      sel.toggle(hash);
    } else {
      sel.pick(hash);
    }
  };

  const onKeyNav = (hash: string, key: "ArrowUp" | "ArrowDown" | "Enter") => {
    if (key === "Enter") return;
    const idx = orderedHashes.indexOf(hash);
    if (idx < 0) return;
    const nextIdx =
      key === "ArrowUp" ? Math.max(0, idx - 1) : Math.min(orderedHashes.length - 1, idx + 1);
    useHistorySelection.getState().pick(orderedHashes[nextIdx]);
    const next = document.querySelector<HTMLLIElement>(
      `li.commit-row[data-hash="${orderedHashes[nextIdx]}"]`,
    );
    next?.focus();
  };

  const selectedCommit = commits?.find((c) => c.hash === primary) ?? null;

  // What the selected commit changed, fetched via the same commit-range-diff
  // endpoint the Commits view's drawer uses — it diffs two commit-ish refs
  // directly (no checkout required), so this is accurate even when
  // `viewedBranch` isn't the one currently checked out.
  const [diffChanges, setDiffChanges] = useState<
    { path: string; type: ChangeType; content: string | null }[] | null
  >(null);
  const [diffLoading, setDiffLoading] = useState(false);
  useEffect(() => {
    let cancelled = false;
    if (!storePath || !selectedCommit) {
      setDiffChanges(null);
      return;
    }
    const parent = selectedCommit.parents[0];
    if (!parent) {
      // Initial commit — nothing to diff against, so it changed everything
      // it introduced. Treat as no highlightable diff for now.
      setDiffChanges([]);
      return;
    }
    setDiffLoading(true);
    api
      .rangeDiff(storePath, parent, selectedCommit.hash)
      .then((res) => {
        if (cancelled) return;
        const commitDiff = res.commits.find((c) => c.hash === selectedCommit.hash);
        setDiffChanges(
          (commitDiff?.changes ?? []).map((c) => ({
            path: c.path,
            type: c.type,
            content: c.new_content ?? c.old_content ?? null,
          })),
        );
        setDiffLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setDiffChanges([]);
        setDiffLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [storePath, selectedCommit]);

  const changedPaths = useMemo(
    () => new Map((diffChanges ?? []).map((c) => [c.path, c.type])),
    [diffChanges],
  );

  // Full taxonomy state as of the selected commit — every path that
  // existed at that point, not just what it touched. Two paths:
  //
  //  - Fast path: the selected commit is the tip of the branch we're
  //    actually checked out on, so `data.memories` (already loaded,
  //    exact) *is* the state as of that commit — no extra request.
  //  - General path: accumulate it by range-diffing from the oldest
  //    commit we've loaded (limit 50) forward through the selected one
  //    (`git log --reverse` order server-side), applying each commit's
  //    added/modified as upserts and deleted as removals in order. This
  //    is only as complete as the loaded commit window — if the oldest
  //    loaded commit still has a parent, there's earlier history we
  //    don't know about, and any path untouched since before that
  //    boundary won't appear. `asOfComplete` tracks which case we're in
  //    so the UI can say so.
  const [asOf, setAsOf] = useState<{ memories: Memory[]; complete: boolean } | null>(
    null,
  );
  const [asOfLoading, setAsOfLoading] = useState(false);
  useEffect(() => {
    let cancelled = false;
    if (!storePath || !selectedCommit || !commits || commits.length === 0) {
      setAsOf(null);
      return;
    }

    const isHeadOfCurrent =
      viewedBranch === currentBranch && commits[0]?.hash === selectedCommit.hash;
    if (isHeadOfCurrent) {
      setAsOf({ memories: data?.memories ?? [], complete: true });
      return;
    }

    const oldest = commits[commits.length - 1];
    const isTrueRoot = oldest.parents.length === 0;
    const baseRef = oldest.parents[0] ?? oldest.hash;
    setAsOfLoading(true);
    api
      .rangeDiff(storePath, baseRef, selectedCommit.hash)
      .then((res) => {
        if (cancelled) return;
        const state = new Map<string, string | null>();
        // Server returns oldest→newest (git log --reverse); apply in
        // order so later changes correctly overwrite/remove earlier ones.
        for (const commitDiff of res.commits) {
          for (const change of commitDiff.changes) {
            if (change.type === "deleted") {
              state.delete(change.path);
            } else {
              state.set(change.path, change.new_content ?? null);
            }
          }
        }
        setAsOf({
          memories: Array.from(state.entries()).map(([path, content]) => ({
            key: `default:${path}`,
            namespace: "default",
            path,
            content,
            value: {},
          })),
          // "Complete" means we've loaded this branch's *entire* history
          // (oldest fetched commit has no parent, i.e. it's the true
          // root) — the only remaining gap is root's own diff, which
          // can't be computed without a parent to diff against (same
          // accepted limitation as the single-commit view below). When
          // `oldest` still has a parent, there's real unknown history
          // before our fetch window and paths untouched since before it
          // won't appear at all.
          complete: isTrueRoot,
        });
        setAsOfLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setAsOf(null);
        setAsOfLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [storePath, selectedCommit, commits, viewedBranch, currentBranch, data]);

  const treeMemories = asOf?.memories ?? [];

  // Stable basis for category→color assignment. `assignCategoryColors`
  // ranks categories alphabetically to pick palette slots, so if the input
  // set changed with every commit selection (as it would using
  // `treeMemories` alone when inspecting a non-current branch — see the
  // comment above), the same category could get reassigned a different
  // color from one commit to the next. Deriving this from the current
  // branch's full memory set instead keeps colors stable across a whole
  // session; it only shifts when that set itself changes (e.g. after a
  // bring-over commit), unioned with whatever the currently-viewed diff
  // touches so a category unique to another branch's history still gets a
  // color rather than falling through to "other".
  const paletteCategories = useMemo(() => {
    const cats = new Set<string>();
    for (const m of data?.memories ?? []) cats.add(categoryOf(m.path));
    for (const m of treeMemories) cats.add(categoryOf(m.path));
    return cats;
  }, [data, treeMemories]);

  const onBranchFromHere = () => {
    if (!selectedCommit || !currentBranch) return;
    useUI.getState().openBranchFromCommit(selectedCommit, currentBranch);
  };

  const [checkingOut, setCheckingOut] = useState<string | null>(null);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const onCheckoutBranch = async (branch: string, event: MouseEvent) => {
    // Stop the chip's own onClick (inspect-only) from also firing.
    event.stopPropagation();
    if (!storePath || branch === currentBranch || checkingOut) return;
    setCheckingOut(branch);
    setCheckoutError(null);
    try {
      await api.checkout(storePath, branch);
      await useStore.getState().refresh();
    } catch (err) {
      setCheckoutError(err instanceof MemoirApiError ? err.message : String(err));
    } finally {
      setCheckingOut(null);
    }
  };

  if (!connected) return null;

  return (
    <div className="history-view">
      <div
        className="history-branch-strip"
        role="tablist"
        aria-label="Branch to inspect"
      >
        {branches.map((b) => (
          <span key={b} className="history-branch-chip-wrap">
            <button
              type="button"
              role="tab"
              aria-selected={viewedBranch === b}
              className={`chip accent history-branch-chip${
                viewedBranch === b ? " is-viewed" : ""
              }${b === currentBranch ? " current" : ""}`}
              onClick={() => {
                setViewedBranch(b);
                useHistorySelection.getState().clear();
              }}
              title={
                b === currentBranch
                  ? `${b} — checked out`
                  : `Inspect ${b}'s history (doesn't check it out)`
              }
            >
              {b}
            </button>
            {b !== currentBranch && (
              <button
                type="button"
                className="history-branch-checkout-btn"
                onClick={(e) => onCheckoutBranch(b, e)}
                disabled={checkingOut !== null}
                title={`Check out ${b}`}
                aria-label={`Check out ${b}`}
              >
                {checkingOut === b ? "…" : "⇄"}
              </button>
            )}
          </span>
        ))}
      </div>
      {checkoutError && (
        <p className="history-detail-note history-checkout-error">
          Checkout failed: {checkoutError}
        </p>
      )}

      <div className="history-body">
        <div className="history-commits">
          {loading && commits === null && (
            <div className="commit-list-empty">Loading commits…</div>
          )}
          {error && (
            <div className="commit-list-empty commit-list-error">
              Failed to load commits: {error}
            </div>
          )}
          {commits && commits.length === 0 && (
            <div className="commit-list-empty">
              <p>No commits yet on {viewedBranch}.</p>
            </div>
          )}
          {commits && commits.length > 0 && (
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
          )}
        </div>

        <div className="history-detail">
          {selectedCommit ? (
            <>
              <div className="history-detail-header">
                <div className="history-detail-title">
                  <code className="history-detail-hash">
                    {selectedCommit.short_hash}
                  </code>
                  <span className="history-detail-message">
                    {selectedCommit.message}
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={onBranchFromHere}
                  disabled={!currentBranch}
                  title={`Create a new branch rooted at ${selectedCommit.short_hash} and switch to it`}
                >
                  Branch from here
                </button>
              </div>
              {asOf && !asOf.complete && (
                <p className="history-detail-note">
                  Tree reflects the last {commits?.length ?? 0} loaded commits — history
                  before that isn't included, so long-untouched paths from further back
                  may be missing.
                </p>
              )}
              {(diffLoading || asOfLoading) && (
                <p className="drawer-empty-hint">Loading changes…</p>
              )}
              <CategoryTree
                memories={treeMemories}
                changedPaths={changedPaths}
                paletteCategories={paletteCategories}
              />
            </>
          ) : (
            <div className="history-detail-empty">
              <p>Select a commit to see what it changed, colored by category.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
